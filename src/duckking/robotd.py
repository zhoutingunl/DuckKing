"""Adapter for the pinned official simulator's local NDJSON protocol."""

import asyncio
import json
import math
import time
from contextlib import suppress
from pathlib import Path


class RobotdBackend:
    kind = "robotd"

    def __init__(self, socket_path: str):
        self.path = str(Path(socket_path).expanduser())
        self.writer = None
        self.reader_task = None
        self.lock = asyncio.Lock()
        self.state = None
        self.received = 0.0
        self.error = "尚未连接官方 robotd"
        self.neutral_head = None

    async def _rpc(self, method, params=None):
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(self.path), 2)
        try:
            request = {"jsonrpc": "2.0", "id": 1, "method": method}
            if params is not None:
                request["params"] = params
            writer.write((json.dumps(request) + "\n").encode())
            await writer.drain()
            response = json.loads(await asyncio.wait_for(reader.readline(), 2))
            if response.get("id") != 1 or "error" in response:
                raise OSError("robotd 拒绝请求或响应不匹配")
            result = response.get("result", {})
            if isinstance(result, dict) and result.get("accepted") is False:
                raise OSError(f"robotd 未接受动作：{result.get('reason', 'unknown')}")
            return result
        finally:
            writer.close()
            await writer.wait_closed()

    async def _notify(self, method, params):
        async with self.lock:
            if self.writer is None or self.writer.is_closing():
                _, self.writer = await asyncio.wait_for(asyncio.open_unix_connection(self.path), 2)
            request = {"jsonrpc": "2.0", "method": method, "params": params}
            self.writer.write((json.dumps(request) + "\n").encode())
            try:
                await self.writer.drain()
            except OSError:
                self.writer.close()
                self.writer = None
                raise

    async def move(self, vx, vyaw):
        if time.monotonic() - self.received > 1:
            raise OSError("robotd 状态过期，拒绝启动动作")
        await self._notify("robot.move", {"vx": vx, "vy": 0.0, "vyaw": vyaw})

    async def head(self, pitch):
        if time.monotonic() - self.received > 1:
            raise OSError("robotd 状态过期，拒绝启动动作")
        # Preserve the daemon's current head intent rather than assuming a joint zero.
        if self.neutral_head is None:
            current = (self.state or {}).get("head")
            if (
                not isinstance(current, list)
                or len(current) != 4
                or not all(
                    isinstance(value, (float, int)) and math.isfinite(value) for value in current
                )
            ):
                raise ValueError("robotd 未提供有效头部状态")
            self.neutral_head = current.copy()
        neck, head, yaw, roll = self.neutral_head
        await self._notify(
            "robot.head",
            {"neck_pitch": neck, "head_pitch": head + pitch, "head_yaw": yaw, "head_roll": roll},
        )

    async def stop(self):
        await self._rpc("robot.stop")
        if self.neutral_head is not None:
            neck, head, yaw, roll = self.neutral_head
            await self._notify(
                "robot.head",
                {"neck_pitch": neck, "head_pitch": head, "head_yaw": yaw, "head_roll": roll},
            )
            self.neutral_head = None

    async def reset(self):
        raise ValueError("官方仿真请使用 duck-sim 重置；本界面不执行机器人上电或断扭矩")

    async def _subscribe(self):
        writer = None
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(self.path), 2)
            writer.write(
                (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "robot.subscribe",
                            "params": {"hz": 20},
                        }
                    )
                    + "\n"
                ).encode()
            )
            await writer.drain()
            while line := await reader.readline():
                message = json.loads(line)
                if "error" in message:
                    raise OSError("robotd 拒绝状态订阅")
                if message.get("method") == "robot.state":
                    self.state = message["params"]
                    self.received = time.monotonic()
                    self.error = ""
            self.error = "robotd 连接已关闭"
        except (OSError, ValueError, KeyError) as exc:
            self.error = f"robotd 未连接（{type(exc).__name__}）"
        finally:
            if writer:
                writer.close()
                with suppress(OSError):
                    await writer.wait_closed()

    async def snapshot(self):
        if self.reader_task is None or self.reader_task.done():
            self.reader_task = asyncio.create_task(self._subscribe())
        connected = bool(self.received and time.monotonic() - self.received < 1)
        # Do not invent world coordinates: the official viewer owns the physics rendering.
        return {
            "kind": self.kind,
            "connected": connected,
            "physics": None,
            "pose": {},
            "velocity": {},
            "telemetry": self.state if connected else None,
            "error": self.error,
            "visualization": "schematic_only",
        }

    async def close(self):
        if self.reader_task:
            self.reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.reader_task
        if self.writer:
            self.writer.close()
            with suppress(OSError):
                await self.writer.wait_closed()
