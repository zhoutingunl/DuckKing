"""A room-owned CPU physics process; external policies cannot block the ASGI loop."""

import asyncio
import json
import os
import sys
import uuid
from collections import OrderedDict
from contextlib import suppress
from pathlib import Path

from .feature_catalog import FeatureCommand, voice_tools

ROOT = Path(__file__).resolve().parents[2]


class FeatureBackend:
    kind, scene, default_speed = "mujoco", "functional", 0.18

    def __init__(self, capability):
        self.capability = capability
        self.process = self.reader = None
        self.pending = {}
        self.state = None
        self.visual = None
        self.revision = uuid.uuid4().hex
        self.error = None
        self.closed = False
        self.task = None
        self.commands = asyncio.Lock()
        self.records = OrderedDict()
        self.ready = asyncio.get_running_loop().create_future()

    @classmethod
    async def create(cls, assets, capability):
        backend = cls(capability)
        env = os.environ.copy()
        env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
        if sys.platform.startswith("linux"):
            # First-person RGB uses Mesa software rendering on headless CPU hosts.
            env.setdefault("MUJOCO_GL", "osmesa")
        env["PYTHONPATH"] = os.pathsep.join(
            filter(
                None,
                (
                    str(ROOT / "src"),
                    str(Path(assets) / "features/python"),
                    env.get("PYTHONPATH"),
                ),
            )
        )
        # All simulator/library prints go to stderr inside the worker; stdout is
        # exclusively bounded newline JSON. No arbitrary module or command path
        # is supplied by HTTP or by a voice tool.
        try:
            backend.process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "duckking.feature_worker",
                str(assets),
                capability,
                backend.revision,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=64 * 1024 * 1024,
            )
            backend.reader = asyncio.create_task(backend._read())
            await asyncio.wait_for(asyncio.shield(backend.ready), 90)
            return backend
        except BaseException:
            await backend.close()
            raise

    async def _read(self):
        try:
            while raw := await self.process.stdout.readline():
                message = json.loads(raw)
                if message.get("type") == "ready":
                    self.visual = message["model"]
                    self.state = message["state"]
                    if not self.ready.done():
                        self.ready.set_result(True)
                elif message.get("type") == "state":
                    self.state = message["state"]
                elif message.get("type") == "reply":
                    future = self.pending.get(message.get("id"))
                    if future and not future.done():
                        if message.get("error"):
                            future.set_exception(ValueError(message["error"]))
                        else:
                            future.set_result(message["result"])
                elif message.get("type") == "error":
                    raise ValueError(message["message"])
            if not self.closed:
                raise ValueError("物理进程已退出，请重置或重新准备场景")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = str(exc) if isinstance(exc, ValueError) else "物理进程通信异常"
            if not self.ready.done():
                self.ready.set_exception(ValueError(self.error))
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(ValueError(self.error))

    async def rpc(self, command):
        if self.closed or self.error:
            raise ValueError(self.error or "场景已释放，请重新准备")
        key = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending[key] = future
        try:
            self.process.stdin.write((json.dumps({"id": key, "command": command}) + "\n").encode())
            await asyncio.wait_for(self.process.stdin.drain(), 5)
            return await asyncio.wait_for(future, 15)
        except (BrokenPipeError, ConnectionResetError, TimeoutError) as exc:
            self.error = "物理进程未响应，请重新准备场景"
            # A timed-out command must not continue unseen in an orphan world.
            await self.close()
            raise ValueError(self.error) from exc
        finally:
            self.pending.pop(key, None)

    async def invoke(self, arguments, *, wait=False):
        command = FeatureCommand.model_validate(arguments).check(self.capability)
        fingerprint = command.model_dump(exclude={"request_id"})
        request_id = command.request_id or uuid.uuid4().hex
        async with self.commands:
            previous = self.records.get(request_id)
            if previous:
                if previous[0] != fingerprint:
                    raise ValueError("相同请求 ID 不能用于不同功能指令")
                result = previous[1]
            else:
                result = await self.rpc({**fingerprint, "request_id": request_id})
                self.records[request_id] = (fingerprint, result)
                while len(self.records) > 60:
                    self.records.popitem(last=False)
        if wait and command.operation == "start":
            for _ in range(300):
                if self.error or self.closed:
                    raise ValueError(self.error or "场景已释放")
                state = self.state or {}
                outcomes = state.get("feature", {}).get("results", [])
                done = next((r for r in outcomes if r["id"] == request_id), None)
                if done:
                    return {**done, "operation_failed": done["status"] != "completed"}
                await asyncio.sleep(0.05)
            return {
                "id": request_id,
                "status": "running",
                "verified": None,
                "pending": True,
                "message": "任务仍在执行，尚无最终结果；可查询状态或停止",
            }
        return result

    def tools(self):
        return voice_tools(self.capability)

    def geometry(self):
        if self.visual is None:
            raise ValueError("模型尚未就绪")
        return self.visual

    async def snapshot(self):
        return {
            **(self.state or {}),
            "kind": self.kind,
            "scene": self.scene,
            "revision": self.revision,
            "connected": not self.closed and not self.error,
            "error": self.error,
        }

    async def prepare(self, action):
        if action.name not in {"stop", "reset"}:
            raise ValueError("请使用当前功能场景工具")

    async def stop(self):
        if not self.closed and not self.error:
            await self.invoke({"operation": "stop"})

    async def reset(self):
        await self.invoke({"operation": "reset"})

    async def close(self):
        self.closed = True
        if self.process and self.process.returncode is None:
            with suppress(ProcessLookupError):
                self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    self.process.kill()
                await self.process.wait()
        if self.reader and self.reader is not asyncio.current_task():
            self.reader.cancel()
            with suppress(asyncio.CancelledError):
                await self.reader
        for future in self.pending.values():
            if not future.done():
                future.set_exception(ValueError("场景已释放"))
        if not self.ready.done():
            self.ready.cancel()
