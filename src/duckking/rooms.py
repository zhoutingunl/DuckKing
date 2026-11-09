"""Bounded visitor-owned rooms; identities persist privately, live state does not."""

import asyncio
import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import HTTPException

from .diagnostics import VoiceDiagnostics
from .experience import VoiceExperience
from .motion import MotionController, PreviewBackend

INTERNAL = object()


class RoomRegistry:
    def __init__(self, primary):
        self.primary = primary
        self.instance = uuid.uuid4().hex
        self.started_at = datetime.now(UTC).isoformat(timespec="seconds")
        primary.preparing = None
        self.limit = primary.settings.max_rooms if primary.motion.backend.kind == "preview" else 1
        self.physics_limit = min(self.limit, primary.settings.max_physics_rooms)
        self.idle_seconds = primary.settings.room_idle_seconds
        self.french_rooms = set(primary.settings.french_rooms)
        self.english_rooms = set(primary.settings.english_rooms)
        self.lock = asyncio.Lock()
        primary.last_used = time.monotonic()
        primary.owner = None
        primary.lease = ""
        self.rooms = {"1": primary}
        if self.limit >= 2:
            self.rooms["2"] = self._make("2")

    def _make(self, number):
        settings = self.primary.settings.for_room(number)
        return SimpleNamespace(
            motion=MotionController(PreviewBackend()), voice=None, scene_motion=None,
            preparing=None,
            owner=None, lease="",
            settings=settings, scene_lock=asyncio.Lock(), viewers=0, reserved_until=0.0,
            last_used=time.monotonic(), voice_diagnostics=VoiceDiagnostics(
                settings.data_dir / "voice.jsonl",
                experience=VoiceExperience(self.primary.experience, number),
            ),
        )

    def get(self, number, *, owner=INTERNAL):
        if (not isinstance(number, str) or number not in self.rooms
                or (owner is not INTERNAL and (
                    owner is None or self.rooms[number].owner != owner))):
            raise HTTPException(404, "房间不存在或已回收，请新建房间")
        room = self.rooms[number]
        room.last_used = time.monotonic()
        return room

    @staticmethod
    def busy(room):
        feature_busy = (room.scene_motion is not None
                        and getattr(room.scene_motion.backend, "scene", None) == "functional"
                        and (room.scene_motion.backend.state or {}).get("feature", {})
                        .get("status") == "running")
        # RL scenes own bounded tasks directly on their physics backends.
        physics_task = (getattr(room.scene_motion.backend, "task", None)
                        if (room.scene_motion
                            and getattr(room.scene_motion.backend, "scene", None)
                            in {"balance", "seesaw"})
                        else None)
        return (feature_busy or getattr(room, "preparing", None) is not None or room.viewers
                or room.voice is not None or room.motion.current is not None
                or (physics_task is not None and not physics_task.done())
                or (room.scene_motion is not None and (room.scene_motion.current is not None
                    or (room.scene_motion.studio is not None
                        and room.scene_motion.studio.task is not None
                        and not room.scene_motion.studio.task.done()))))

    def owned(self, owner):
        return {number: room for number, room in self.rooms.items()
                if owner is INTERNAL or (owner is not None and room.owner == owner)}

    def scopes(self, owner):
        return tuple({room.lease for room in self.owned(owner).values()})

    def snapshot(self, *, owner=INTERNAL):
        rooms = self.owned(owner)
        return {"instance": self.instance, "rooms": [{"id": number, "viewers": room.viewers,
                           "voice_busy": room.voice is not None,
                           "physics": room.scene_motion is not None}
                          for number, room in rooms.items()],
                "capacity": self.limit, "physics_capacity": self.physics_limit,
                "physics_active": sum(r.scene_motion is not None for r in rooms.values()),
                "idle_seconds": self.idle_seconds}

    def claim_result(self, number, language):
        result = {"room": number}
        if language in {"fr", "en"}:
            from .voice_profiles import profiles
            available = f"language_{language}" in profiles(self.primary.settings)["agents"]
            result["voice_language"] = language if available else "default"
        return result

    def assign(self, room, number, owner):
        if owner is INTERNAL or room.owner == owner:
            return
        # Reusing a numeric slot must not reveal the previous visitor's history.
        backend = room.motion.backend
        room.motion = MotionController(
            PreviewBackend() if backend.kind == "preview" else backend
        )
        room.owner = owner
        room.lease = uuid.uuid4().hex
        room.voice_diagnostics = VoiceDiagnostics(
            room.settings.data_dir / "voice.jsonl", restore=False,
            experience=VoiceExperience(self.primary.experience, number, scope=room.lease),
        )

    async def claim(self, *, create=False, language="zh", owner=INTERNAL):
        if owner is None:
            raise HTTPException(401, "请先建立访客会话")
        if language not in {"zh", "fr", "en"}:
            raise HTTPException(422, "不支持的房间语言")
        # Iterate the configured order; the sets above are only for membership.
        voice_rooms = {
            "fr": self.primary.settings.french_rooms,
            "en": self.primary.settings.english_rooms,
        }.get(language, ())
        await self.reap()
        async with self.lock:
            now = time.monotonic()
            if voice_rooms:
                # Each configured voice room has its own provisioned identity
                # and agent language. Never share a busy voice room with another
                # visitor.
                for number in voice_rooms:
                    room = self.rooms.get(number)
                    if room is None and len(self.rooms) < self.limit:
                        room = self._make(number)
                        self.rooms[number] = room
                    if room is not None and (owner is INTERNAL or room.owner in {None, owner}) \
                            and not create and not self.busy(room) \
                            and room.reserved_until <= now:
                        self.assign(room, number, owner)
                        room.reserved_until = now + 15
                        room.last_used = now
                        return {"room": number, "voice_language": language}
            if not create:
                for number, room in self.rooms.items():
                    if number in self.french_rooms or number in self.english_rooms:
                        continue
                    if owner is not INTERNAL and room.owner not in {None, owner}:
                        continue
                    if not self.busy(room) and room.reserved_until <= now:
                        self.assign(room, number, owner)
                        room.reserved_until = now + 15
                        room.last_used = now
                        return self.claim_result(number, language)
            for index in range(1, self.limit + 1):
                number = str(index)
                existing = self.rooms.get(number)
                if (owner is not INTERNAL and existing is not None and existing.owner is None
                        and number not in self.french_rooms | self.english_rooms
                        and not self.busy(existing) and existing.reserved_until <= now):
                    self.assign(existing, number, owner)
                    existing.reserved_until = now + 15
                    existing.last_used = now
                    return self.claim_result(number, language)
                if number not in self.rooms and number not in self.french_rooms \
                        and number not in self.english_rooms:
                    room = self._make(number)
                    self.assign(room, number, owner)
                    room.reserved_until = now + 15
                    self.rooms[number] = room
                    return self.claim_result(number, language)
            raise HTTPException(409, f"房间容量暂满（{self.limit}），请稍后重试")

    async def reap(self):
        async with self.lock:
            for number, room in list(self.rooms.items()):
                if (self.busy(room) or room.reserved_until > time.monotonic()
                        or time.monotonic() - room.last_used < self.idle_seconds):
                    continue
                async with room.scene_lock:
                    if self.busy(room) or time.monotonic() - room.last_used < self.idle_seconds:
                        continue
                    # Rooms 1 and 2 are permanent; configured voice rooms keep
                    # their provisioned identities and are never reclaimed.
                    if number not in {"1", "2"} | self.french_rooms | self.english_rooms:
                        del self.rooms[number]
                        await room.motion.close()
                    if room.scene_motion:
                        controller, room.scene_motion = room.scene_motion, None
                        await controller.close()
                    room.owner = None
                    room.reserved_until = 0.0

    async def watch(self):
        while True:
            await asyncio.sleep(15)
            await self.reap()
