"""Bounded, cancellable motion shared by UI actions and MCP tools."""

import asyncio
import math
import time
import uuid
from collections import OrderedDict, deque
from contextlib import suppress
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .choreography import CHOREOGRAPHIES, DEFAULT_DURATION, MIN_DURATION, sample

SCENE_ACTIONS = {
    "scene_ball",
    "scene_duo",
    "kick_left",
    "kick_right",
    "find_companion",
    "duo_walk",
    "collide",
    "chorus",
}


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: Literal[
        "nod",
        "walk",
        "turn_left",
        "turn_right",
        "stop",
        "reset",
        "flash_step",
        "bear_shake",
        "scene_ball",
        "scene_duo",
        "kick_left",
        "kick_right",
        "find_companion",
        "duo_walk",
        "collide",
        "chorus",
    ]
    duration: float = Field(default=1.2, ge=0.2, le=3.0)
    speed: float | None = Field(default=None, ge=0.02, le=0.4)
    target: Literal["a", "b", "both"] = "a"
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def choreography_defaults(cls, data):
        fixed = {
            "kick_left": 2,
            "kick_right": 2,
            "chorus": 3,
            "duo_walk": 3,
            "collide": 3,
            "find_companion": 0.6,
            "scene_ball": 0.2,
            "scene_duo": 0.2,
        }
        if isinstance(data, dict) and data.get("name") in fixed and "duration" not in data:
            return data | {"duration": fixed[data["name"]]}
        if isinstance(data, dict) and data.get("name") in CHOREOGRAPHIES and "duration" not in data:
            return data | {"duration": DEFAULT_DURATION}
        return data

    @model_validator(mode="after")
    def choreography_timing(self):
        if self.name in SCENE_ACTIONS and self.speed is not None:
            raise ValueError("场景动作使用固定策略速度，不接受 speed 参数")
        fixed = {
            "kick_left": 2,
            "kick_right": 2,
            "chorus": 3,
            "find_companion": 0.6,
            "scene_ball": 0.2,
            "scene_duo": 0.2,
        }
        if self.name in fixed and self.duration != fixed[self.name]:
            raise ValueError("此场景动作使用固定时长")
        if self.name in CHOREOGRAPHIES and self.duration < MIN_DURATION:
            raise ValueError("组合动作至少需要 2.4 秒，不能压缩成高速抖动")
        if self.name in CHOREOGRAPHIES and self.speed is not None:
            raise ValueError("组合动作使用固定编排速度，不接受 speed 参数")
        return self


class Backend(Protocol):
    kind: str
    default_speed: float

    async def move(self, vx: float, vyaw: float, vy: float = 0.0) -> None: ...
    async def head(self, pitch: float, yaw: float = 0.0, roll: float = 0.0) -> None: ...
    async def body_pose(self, z: float, roll: float, pitch: float, active: bool) -> None: ...
    async def stop(self) -> None: ...
    async def reset(self) -> None: ...
    async def snapshot(self) -> dict: ...
    async def close(self) -> None: ...


class PreviewBackend:
    """Kinematic animation only. No contacts, balance model, or learned gait."""

    kind = "preview"
    default_speed = 0.12

    def __init__(self):
        self.x = self.z = self.yaw = self.pitch = self.vx = self.vyaw = 0.0
        self.vy = self.head_yaw = self.head_roll = 0.0
        self.body_z = self.body_roll = self.body_pitch = 0.0
        self.updated = time.monotonic()

    def _advance(self):
        now = time.monotonic()
        dt = min(now - self.updated, 0.2)
        self.updated = now
        self.yaw += self.vyaw * dt
        self.x += (self.vx * math.sin(self.yaw) + self.vy * math.cos(self.yaw)) * dt
        self.z += (self.vx * math.cos(self.yaw) - self.vy * math.sin(self.yaw)) * dt

    async def move(self, vx, vyaw, vy=0.0):
        self._advance()
        self.vx, self.vyaw, self.vy = vx, vyaw, vy

    async def head(self, pitch, yaw=0.0, roll=0.0):
        self.pitch, self.head_yaw, self.head_roll = pitch, yaw, roll

    async def body_pose(self, z, roll, pitch, active):
        self.body_z, self.body_roll, self.body_pitch = (z, roll, pitch) if active else (0, 0, 0)

    async def stop(self):
        self._advance()
        self.vx = self.vyaw = self.pitch = 0.0
        self.vy = self.head_yaw = self.head_roll = 0.0
        self.body_z = self.body_roll = self.body_pitch = 0.0

    async def reset(self):
        await self.stop()
        self.x = self.z = self.yaw = 0.0

    async def snapshot(self):
        self._advance()
        return {
            "kind": self.kind,
            "connected": True,
            "physics": False,
            "pose": {
                "x": self.x,
                "z": self.z,
                "yaw": self.yaw,
                "pitch": self.pitch,
                "head_yaw": self.head_yaw,
                "head_roll": self.head_roll,
                "body_z": self.body_z,
                "body_roll": self.body_roll,
                "body_pitch": self.body_pitch,
            },
            "velocity": {"forward": self.vx, "lateral": self.vy, "yaw": self.vyaw},
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
            if self.backend.kind == "mujoco":
                await self.backend.prepare(action)
            elif action.name in SCENE_ACTIONS or action.target != "a":
                raise ValueError("此动作需要官方 MuJoCo 场景，不会退回动画预览")
            if action.name in SCENE_ACTIONS:
                record["outcome"] = await self.backend.perform(action)
                if record["outcome"].get("verified") is False:
                    raise ValueError(record["outcome"]["message"])
            elif action.name == "reset":
                await self.backend.reset()
            elif action.name == "stop":
                await self.backend.stop()
            else:
                started = time.monotonic()
                while (elapsed := time.monotonic() - started) < action.duration:
                    if action.name in CHOREOGRAPHIES:
                        frame = sample(action.name, elapsed, action.duration)
                        if record.get("phase") != frame.phase:
                            record["phase"] = frame.phase
                            self.event(
                                "phase",
                                f"{CHOREOGRAPHIES[action.name]} · {frame.phase}",
                                action_id=action.request_id,
                            )
                        await self.backend.body_pose(
                            frame.body_z, frame.body_roll, frame.body_pitch, frame.body_active
                        )
                        await self.backend.head(frame.head_pitch, frame.head_yaw, frame.head_roll)
                        await self.backend.move(frame.forward, frame.turn, frame.lateral)
                    elif action.name == "nod":
                        # Smooth, bounded head trajectory, not a new learned motion policy.
                        pitch = 0.18 * math.sin(elapsed / action.duration * math.tau * 2)
                        await self.backend.head(pitch)
                    else:
                        speed = (
                            action.speed if action.speed is not None else self.backend.default_speed
                        )
                        vx = speed if action.name == "walk" else 0.0
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
