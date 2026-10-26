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
from .motion_catalog import SKILL_DURATIONS, TRANSLATIONS

STAGE_DURATIONS = {"stage_gather": 44, "stage_roll": 28, "stage_dance": 12, "stage_poke": 0.2}

SCENE_ACTIONS = {
    *STAGE_DURATIONS,
    "scene_turntable",
    "spin_slow",
    "spin_medium",
    "spin_fast",
    "spin_stop",
    "scene_stage",
    *SKILL_DURATIONS,
    "scene_skills",
    "scene_rollers",
    "sit",
    "stand",
    "scene_seated",
    "seated_show",
    "seated_ready",
    "seated_solo",
    "scene_table",
    "table_show",
    "scene_ball",
    "scene_duo",
    "scene_carry",
    "pick_up",
    "carry",
    "put_down",
    "ball_prepare_left",
    "ball_prepare_right",
    "ball_shoot_left",
    "ball_shoot_right",
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
        "scene_turntable",
        "spin_slow",
        "spin_medium",
        "spin_fast",
        "spin_stop",
        "scene_stage",
        "stage_gather",
        "stage_roll",
        "stage_dance",
        "stage_poke",
        "roulade",
        "ground_pick",
        "skate",
        "roller_crouch",
        "yawn",
        "idle_on",
        "idle_off",
        "scene_skills",
        "scene_rollers",
        "backward",
        "strafe_left",
        "strafe_right",
        "shake_head",
        "tilt_head",
        "sit",
        "stand",
        "scene_seated",
        "seated_show",
        "seated_ready",
        "seated_solo",
        "scene_table",
        "table_show",
        "look_left",
        "look_right",
        "look_forward",
        "look_down",
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
        "scene_carry",
        "pick_up",
        "carry",
        "put_down",
        "ball_prepare_left",
        "ball_prepare_right",
        "ball_shoot_left",
        "ball_shoot_right",
        "kick_left",
        "kick_right",
        "find_companion",
        "duo_walk",
        "collide",
        "chorus",
    ]
    duration: float = Field(default=1.2, ge=0.2, le=44)
    speed: float | None = Field(default=None, ge=0.02, le=0.4)
    target: Literal["a", "b", "c", "d", "both"] = "a"
    member: Literal["a", "b", "c", "d", "selected", "leftmost"] = "selected"
    members: list[Literal["a", "b", "c", "d"]] | None = Field(
        default=None, min_length=1, max_length=4)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def choreography_defaults(cls, data):
        fixed = {
            **STAGE_DURATIONS,
            "scene_turntable": 0.2,
            "spin_slow": 0.2,
            "spin_medium": 0.2,
            "spin_fast": 0.2,
            "spin_stop": 0.2,
            "scene_stage": 0.2,
            **SKILL_DURATIONS,
            "scene_skills": 0.2,
            "scene_rollers": 0.2,
            "sit": 3,
            "stand": 3,
            "scene_seated": 0.2,
            "seated_show": 44,
            "seated_ready": 3,
            "seated_solo": 14,
            "scene_table": 0.2,
            "table_show": 36,
            "ball_prepare_left": 0.6,
            "ball_prepare_right": 0.6,
            "ball_shoot_left": 2,
            "ball_shoot_right": 2,
            "kick_left": 2,
            "kick_right": 2,
            "chorus": 3,
            "duo_walk": 3,
            "collide": 3,
            "find_companion": 0.6,
            "scene_ball": 0.2,
            "scene_duo": 0.2,
            "scene_carry": 0.2,
            "pick_up": 2.2,
            "carry": 3,
            "put_down": 4.5,
        }
        if isinstance(data, dict) and data.get("name") in fixed and "duration" not in data:
            return data | {"duration": fixed[data["name"]]}
        if isinstance(data, dict) and data.get("name") in CHOREOGRAPHIES and "duration" not in data:
            return data | {"duration": DEFAULT_DURATION}
        return data

    @model_validator(mode="after")
    def choreography_timing(self):
        if self.members is not None:
            if (self.name not in {"stage_gather", "stage_roll", "stage_dance"}
                    or self.member != "selected"):
                raise ValueError("members 仅用于四鸭发布会群体动作，不能同时指定 member")
            if len(set(self.members)) != len(self.members):
                raise ValueError("翻滚成员不能重复")
        if not self.name.startswith("stage_") and self.member != "selected":
            raise ValueError("member 仅用于四鸭发布会")
        if self.name.startswith("stage_") and self.target != "a":
            raise ValueError("四鸭发布会使用 member 指定成员")
        if self.target in {"c", "d"} and self.name != "seated_solo":
            raise ValueError("鸭 C / D 仅用于语音独唱")
        if self.name == "seated_solo" and self.target == "both":
            raise ValueError("一次只能指定一位独唱者")
        if (
            self.name in {"table_show", "scene_table", "seated_show", "scene_seated"}
            and self.target != "a"
        ):
            raise ValueError("桌上编排统一控制四只鸭，不接受单独指定成员")
        if (
            self.name
            not in {
                "put_down",
                "table_show",
                "seated_show",
                "seated_solo",
                *SKILL_DURATIONS,
                *STAGE_DURATIONS,
            }
            and self.duration > 3
        ):
            raise ValueError("此动作最长为 3 秒")
        if self.name in SCENE_ACTIONS and self.speed is not None:
            raise ValueError("场景动作使用固定策略速度，不接受 speed 参数")
        fixed = {
            **STAGE_DURATIONS,
            "scene_turntable": 0.2,
            "spin_slow": 0.2,
            "spin_medium": 0.2,
            "spin_fast": 0.2,
            "spin_stop": 0.2,
            "scene_stage": 0.2,
            **SKILL_DURATIONS,
            "scene_skills": 0.2,
            "scene_rollers": 0.2,
            "sit": 3,
            "stand": 3,
            "scene_seated": 0.2,
            "seated_show": 44,
            "seated_ready": 3,
            "seated_solo": 14,
            "scene_table": 0.2,
            "table_show": 36,
            "ball_prepare_left": 0.6,
            "ball_prepare_right": 0.6,
            "ball_shoot_left": 2,
            "ball_shoot_right": 2,
            "kick_left": 2,
            "kick_right": 2,
            "chorus": 3,
            "find_companion": 0.6,
            "scene_ball": 0.2,
            "scene_duo": 0.2,
            "scene_carry": 0.2,
            "pick_up": 2.2,
            "carry": 3,
            "put_down": 4.5,
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
        self.studio = None

    def event(self, kind: str, text: str, **data):
        self.event_sequence += 1
        self.events.append(
            {"id": self.event_sequence, "time": time.time(), "kind": kind, "text": text, **data}
        )

    async def submit(self, action: Action, *, owner=None) -> dict:
        if self.studio and owner is not self.studio and action.request_id not in self.records:
            await self.studio.external(action)
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
            if action.name in SCENE_ACTIONS or (
                self.backend.kind == "mujoco" and action.name in TRANSLATIONS
            ):
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
                    elif action.name.startswith("look_"):
                        pitch, yaw = {"look_left": (0, 0.35), "look_right": (0, -0.35),
                                      "look_forward": (0, 0), "look_down": (0.18, 0)}[action.name]
                        blend = min(1, elapsed / 0.3)
                        await self.backend.head(pitch * blend, yaw * blend)
                    elif action.name in {"nod", "shake_head", "tilt_head"}:
                        # Smooth, bounded head trajectory, not a new learned motion policy.
                        phase = elapsed / action.duration
                        if action.name == "nod":
                            await self.backend.head(0.18 * math.sin(phase * math.tau * 2))
                        elif action.name == "shake_head":
                            await self.backend.head(0, 0.30 * math.sin(phase * math.tau * 2))
                        else:
                            await self.backend.head(0, 0, 0.20 * math.sin(phase * math.pi) ** 2)
                    else:
                        speed = (
                            action.speed if action.speed is not None else self.backend.default_speed
                        )
                        vx = (
                            speed
                            if action.name == "walk"
                            else -min(speed, 0.20)
                            if action.name == "backward"
                            else 0.0
                        )
                        lateral = min(speed, 0.15) * {"strafe_left": 1, "strafe_right": -1}.get(
                            action.name, 0
                        )
                        yaw = {"turn_left": 0.6, "turn_right": -0.6}.get(action.name, 0.0)
                        await self.backend.move(vx, yaw, lateral)
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
            **({"studio": self.studio.snapshot()} if self.studio else {}),
        }

    async def close(self):
        if self.studio:
            await self.studio.close()
        async with self.lock:
            await self._cancel()
            await self.backend.close()
