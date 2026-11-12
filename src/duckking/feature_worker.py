"""Private subprocess protocol for functional scenes. Never listens on a network socket."""

import asyncio
import json
import sys
import time
import traceback
from collections import deque
from contextlib import suppress
from pathlib import Path

from .feature_catalog import CATALOG, FeatureCommand


class Worker:
    def __init__(self, world, capability, revision, output):
        self.world, self.capability = world, capability
        self.revision, self.output = revision, output
        self.task = None
        self.results = deque(maxlen=60)
        self.current = {"status": "idle", "verified": None, "phase": "ready"}
        self.lock = asyncio.Lock()

    def emit(self, message):
        self.output.write(json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n")
        self.output.flush()

    async def snapshot(self):
        state = await self.world.snapshot()
        return {
            **state,
            "scene": "functional",
            "revision": self.revision,
            "feature": {
                **self.current,
                "capability": self.capability,
                "source": CATALOG[self.capability]["source"],
                "observation": CATALOG[self.capability]["observation"],
                "results": list(self.results),
                "metrics": self.world.metrics,
            },
        }

    async def cancel(self):
        if self.task and not self.task.done():
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            if self.current["status"] == "running":
                self.current.update(
                    status="cancelled",
                    phase="cancelled",
                    verified=False,
                    message="任务已取消",
                    finished_at=time.time(),
                )
                self.results.append(dict(self.current))
        self.task = None
        await self.world.stop()

    async def run(self, command):
        result = self.current
        try:
            async with asyncio.timeout(600 if self.capability == "circus" else 180):
                outcome = await self.world.perform(command)
            verified = outcome.get("verified") is True
            result.update(
                status="completed" if verified else "failed",
                verified=verified,
                outcome=outcome,
                message=outcome.get("message", "任务结束"),
            )
        except asyncio.CancelledError:
            result.update(status="cancelled", verified=False, message="任务已取消")
        except TimeoutError:
            result.update(status="failed", verified=False, message="任务执行超时，已暂停")
        except Exception as exc:
            traceback.print_exc()
            result.update(
                status="failed",
                verified=False,
                message=str(exc) if isinstance(exc, ValueError) else "任务执行异常",
            )
        finally:
            try:
                await self.world.stop()
            except Exception:
                result.update(status="failed", verified=False, message="停止未得到确认")
            result["finished_at"] = time.time()
            result["phase"] = result["status"]
            self.results.append(dict(result))
            self.emit({"type": "state", "state": await self.snapshot()})

    async def handle(self, message):
        if not isinstance(message, dict) or not isinstance(message.get("id"), str):
            raise ValueError("功能场景请求格式无效")
        key = message["id"]
        try:
            command = FeatureCommand.model_validate(message.get("command")).check(self.capability)
            async with self.lock:
                if command.operation != "status":
                    await self.cancel()
                if command.operation == "reset":
                    await self.world.reset()
                    self.current = {"status": "idle", "verified": None, "phase": "ready"}
                elif command.operation == "start":
                    self.world.metrics = {}
                    self.current = {
                        "id": command.request_id,
                        "action": command.action,
                        "status": "running",
                        "verified": None,
                        "started_at": time.time(),
                        "phase": "running",
                    }
                if command.operation != "status":
                    # Publish the accepted state before starting policy work.
                    # A first inference may be slow; readers must not see the
                    # old idle snapshot after receiving a successful RPC reply.
                    self.emit({"type": "state", "state": await self.snapshot()})
                if command.operation == "start":
                    self.task = asyncio.create_task(self.run(command))
                result = dict(self.current)
            self.emit({"type": "reply", "id": key, "result": result})
        except ValueError as exc:
            self.emit({"type": "reply", "id": key, "error": str(exc)})

    async def receive(self, reader):
        while True:
            raw = await reader.readline()
            if not raw:
                return
            if len(raw) > 16384 or not raw.endswith(b"\n"):
                raise ValueError("功能场景请求过长或协议分帧无效")
            await self.handle(json.loads(raw))

    async def stream(self):
        while True:
            self.emit({"type": "state", "state": await self.snapshot()})
            await asyncio.sleep(0.05 if self.task and not self.task.done() else 0.5)


async def main(output):
    assets, capability, revision = sys.argv[1:4]
    variant = int(sys.argv[4]) if len(sys.argv) == 5 else None
    if capability not in CATALOG:
        raise ValueError("未知功能场景")
    assets = await asyncio.to_thread(Path(assets).resolve)
    sys.path.insert(0, str(assets / "features/bam"))
    from .feature_worlds import make_world

    world = make_world(assets, capability, **({"variant": variant} if variant is not None else {}))
    worker = Worker(world, capability, revision, output)
    visual = world.geometry()
    visual.update(revision=revision, source="official_microduck_physics", physics=True)
    worker.emit({"type": "ready", "model": visual, "state": await worker.snapshot()})
    reader = asyncio.StreamReader(limit=16384)
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer
    )
    stream = asyncio.create_task(worker.stream())
    receiver = asyncio.create_task(worker.receive(reader))
    try:
        done, _ = await asyncio.wait({stream, receiver}, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    finally:
        transport.close()
        for task in (stream, receiver):
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        await worker.cancel()
        await world.close()


if __name__ == "__main__":
    protocol_output, sys.stdout = sys.stdout, sys.stderr
    try:
        asyncio.run(main(protocol_output))
    except Exception:
        traceback.print_exc()
        protocol_output.write(
            json.dumps(
                {
                    "type": "error",
                    "message": (
                        "功能场景准备失败，请检查对应模型资源和 CPU 运行环境；未切换为动画预览。"
                    ),
                }
            )
            + "\n"
        )
        protocol_output.flush()
        sys.exit(1)
