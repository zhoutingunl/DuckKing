"""Bounded, cancellable motion shared by UI actions and MCP tools."""

import asyncio
import math
import time
import uuid
from collections import OrderedDict, deque
from contextlib import suppress
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: Literal["nod", "walk", "turn_left", "turn_right", "stop", "reset"]
    duration: float = Field(default=1.2, ge=0.2, le=3.0)
    speed: float = Field(default=0.12, ge=0.02, le=0.2)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1, max_length=100)


class Backend(Protocol):
    kind: str

    async def move(self, vx: float, vyaw: float) -> None: ...
    async def head(self, pitch: float) -> None: ...
    async def stop(self) -> None: ...
    async def reset(self) -> None: ...
    async def snapshot(self) -> dict: ...
    async def close(self) -> None: ...


class PreviewBackend:
    """Kinematic animation only. No contacts, balance model, or learned gait."""

    kind = "preview"

    def __init__(self):
        self.x = self.z = self.yaw = self.pitch = self.vx = self.vyaw = 0.0
        self.updated = time.monotonic()

    def _advance(self):
        now = time.monotonic()
        dt = min(now - self.updated, 0.2)
        self.updated = now
        self.yaw += self.vyaw * dt
        self.x += self.vx * math.sin(self.yaw) * dt
        self.z += self.vx * math.cos(self.yaw) * dt

    async def move(self, vx, vyaw):
        self._advance()
        self.vx, self.vyaw = vx, vyaw

    async def head(self, pitch):
        self.pitch = pitch

    async def stop(self):
        self._advance()
        self.vx = self.vyaw = self.pitch = 0.0

    async def reset(self):
        await self.stop()
        self.x = self.z = self.yaw = 0.0

    async def snapshot(self):
        self._advance()
        return {
            "kind": self.kind,
            "connected": True,
            "physics": False,
            "pose": {"x": self.x, "z": self.z, "yaw": self.yaw, "pitch": self.pitch},
            "velocity": {"forward": self.vx, "yaw": self.vyaw},
        }

    async def close(self):
        await self.stop()


class MotionController:
    def __init__(self, backend: Backend):
        self.backend = backend
        self.lock = asyncio.Lock()
        self.task: asyncio.Task | None = None
        self.current: dict | None = None
        self.records: OrderedDict[str, dict] = OrderedDict()
        self.done: dict[str, asyncio.Future] = {}
        self.events = deque(maxlen=60)
        self.event_sequence = 0
        self.failure: str | None = None

    def event(self, kind: str, text: str, **data):
        self.event_sequence += 1
        self.events.append(
            {"id": self.event_sequence, "time": time.time(), "kind": kind, "text": text, **data}
        )

    async def submit(self, action: Action) -> dict:
        async with self.lock:
            previous = self.records.get(action.request_id)
            fingerprint = action.model_dump(exclude={"request_id"})
            if previous:
                if previous["input"] != fingerprint:
                    raise ValueError("相同请求 ID 不能用于不同动作")
                return dict(previous)
            await self._cancel()
            record = {
                "id": action.request_id,
                "name": action.name,
                "input": fingerprint,
                "status": "running",
                "started_at": time.time(),
            }
            self.records[action.request_id] = record
            self.done[action.request_id] = asyncio.get_running_loop().create_future()
            while len(self.records) > 200:
                key, _ = self.records.popitem(last=False)
                self.done.pop(key, None)
            self.current = record
            self.failure = None
            self.event("action", f"开始动作 · {action.name}", action_id=action.request_id)
            self.task = asyncio.create_task(self._run(action, record))
            return dict(record)

    async def _cancel(self):
        if self.task and not self.task.done():
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            # A task cancelled before its first scheduling turn never enters its finally block.
            if self.current and self.current["status"] == "running":
                record = self.current
                record.update(status="cancelled", finished_at=time.time())
                self.done[record["id"]].set_result(dict(record))
                self.current = None
                await self.backend.stop()
        self.task = None

    async def _run(self, action: Action, record: dict):
        try:
            if action.name == "reset":
                await self.backend.reset()
            elif action.name == "stop":
                await self.backend.stop()
            else:
                started = time.monotonic()
                while (elapsed := time.monotonic() - started) < action.duration:
                    if action.name == "nod":
                        # Smooth, bounded head trajectory, not a new learned motion policy.
                        pitch = 0.18 * math.sin(elapsed / action.duration * math.tau * 2)
                        await self.backend.head(pitch)
                    else:
                        vx = action.speed if action.name == "walk" else 0.0
                        yaw = {"turn_left": 0.6, "turn_right": -0.6}.get(action.name, 0.0)
                        await self.backend.move(vx, yaw)
                    await asyncio.sleep(0.05)
            record["status"] = "completed"
        except asyncio.CancelledError:
            record["status"] = "cancelled"
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
            self.failure = str(exc)
        finally:
            try:
                await self.backend.stop()
            except Exception as exc:
                record["status"] = "failed"
                record["error"] = f"停止确认失败：{exc}"
                self.failure = record["error"]
            record["finished_at"] = time.time()
            self.event(
                "result",
                f"{action.name} · {record['status']}",
                action_id=action.request_id,
                status=record["status"],
            )
            if self.current is record:
                self.current = None
            future = self.done[action.request_id]
            if not future.done():
                future.set_result(dict(record))

    async def wait(self, request_id: str) -> dict:
        return await asyncio.shield(self.done[request_id])

    async def snapshot(self):
        return {
            "backend": await self.backend.snapshot(),
            "action": dict(self.current) if self.current else None,
            "error": self.failure,
            "events": list(self.events),
        }

    async def close(self):
        async with self.lock:
            await self._cancel()
            await self.backend.close()
