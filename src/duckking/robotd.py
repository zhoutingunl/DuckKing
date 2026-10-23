"""Adapter for the pinned official simulator's local NDJSON protocol."""

import asyncio
import json
import math
import time
from contextlib import suppress
from pathlib import Path


class RobotdBackend:
    kind = "robotd"
    default_speed = 0.35

    def __init__(self, socket_path: str):
        self.path = str(Path(socket_path).expanduser())
        self.writer = None
        self.reader_task = None
        self.lock = asyncio.Lock()
        self.state = None
        self.received = 0.0
        self.error = "尚未连接官方 robotd"
        self.neutral_head = None
        self.pose_active = False

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

    def _ensure_ready(self):
        if time.monotonic() - self.received > 1:
            raise OSError("robotd 状态过期，拒绝启动动作")
        safety = (self.state or {}).get("safety", {})
        if any(safety.get(key) for key in ("fallen", "limp", "picked_up")):
            raise OSError("机器人姿态不允许继续动作")

    async def move(self, vx, vyaw, vy=0.0):
        self._ensure_ready()
        await self._notify("robot.move", {"vx": vx, "vy": vy, "vyaw": vyaw})

    async def head(self, pitch, yaw=0.0, roll=0.0):
        self._ensure_ready()
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
        neck, head, base_yaw, base_roll = self.neutral_head
        await self._notify(
            "robot.head",
            {
                "neck_pitch": neck,
                "head_pitch": max(-1.1, min(1.1, head + pitch)),
                "head_yaw": max(-1.4, min(1.4, base_yaw + yaw)),
                "head_roll": max(-0.31, min(0.31, base_roll + roll)),
            },
        )

    async def body_pose(self, z, roll, pitch, active):
        self._ensure_ready()
        if not all(math.isfinite(value) for value in (z, roll, pitch)) or not (
            -0.025 <= z <= 0.010 and abs(roll) <= 0.26 and abs(pitch) <= 0.26
        ):
            raise ValueError("身体姿态超出当前模型的训练范围")
        # Keep the restore flag on if a write fails after possibly reaching robotd.
        self.pose_active = self.pose_active or active
        await self._notify("robot.pose", {"z": z, "roll": roll, "pitch": pitch, "active": active})
        self.pose_active = active

    async def stop(self):
        errors = []
        try:
            await self._rpc("robot.stop")
        except OSError as exc:
            errors.append(str(exc))
        if self.pose_active:
            try:
                await self._notify(
                    "robot.pose", {"z": 0.0, "roll": 0.0, "pitch": 0.0, "active": False}
                )
                self.pose_active = False
            except OSError as exc:
                errors.append(str(exc))
        if self.neutral_head is not None:
            neck, head, yaw, roll = self.neutral_head
            try:
                await self._notify(
                    "robot.head",
                    {"neck_pitch": neck, "head_pitch": head, "head_yaw": yaw, "head_roll": roll},
                )
                self.neutral_head = None
            except OSError as exc:
                errors.append(str(exc))
        if errors:
            raise OSError("; ".join(errors))

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
            "velocity": {"forward": ((self.state or {}).get("move", {}).get("applied") or [0])[0]}
            if connected
            else {},
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
