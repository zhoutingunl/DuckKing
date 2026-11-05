"""Bounded public demo rooms; identities persist privately, live state does not."""

import asyncio
import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import HTTPException

from .diagnostics import VoiceDiagnostics
from .experience import VoiceExperience
from .motion import MotionController, PreviewBackend


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
        self.rooms = {"1": primary}
        if self.limit >= 2:
            self.rooms["2"] = self._make("2")

    def _make(self, number):
        settings = self.primary.settings.for_room(number)
        return SimpleNamespace(
            motion=MotionController(PreviewBackend()), voice=None, scene_motion=None,
            preparing=None,
            settings=settings, scene_lock=asyncio.Lock(), viewers=0, reserved_until=0.0,
            last_used=time.monotonic(), voice_diagnostics=VoiceDiagnostics(
                settings.data_dir / "voice.jsonl",
                experience=VoiceExperience(self.primary.experience, number),
            ),
        )

    def get(self, number):
        if not isinstance(number, str) or number not in self.rooms:
            raise HTTPException(404, "房间不存在或已回收，请新建房间")
        room = self.rooms[number]
        room.last_used = time.monotonic()
        return room

    @staticmethod
    def busy(room):
        # RL scenes own bounded tasks directly on their physics backends.
        physics_task = (getattr(room.scene_motion.backend, "task", None)
                        if (room.scene_motion
                            and getattr(room.scene_motion.backend, "scene", None)
                            in {"balance", "seesaw"})
                        else None)
        return (getattr(room, "preparing", None) is not None or room.viewers
                or room.voice is not None or room.motion.current is not None
                or (physics_task is not None and not physics_task.done())
                or (room.scene_motion is not None and (room.scene_motion.current is not None
                    or (room.scene_motion.studio is not None
                        and room.scene_motion.studio.task is not None
                        and not room.scene_motion.studio.task.done()))))

    def snapshot(self):
        return {"instance": self.instance, "rooms": [{"id": number, "viewers": room.viewers,
                           "voice_busy": room.voice is not None,
                           "physics": room.scene_motion is not None}
                          for number, room in self.rooms.items()],
                "capacity": self.limit, "physics_capacity": self.physics_limit,
                "physics_active": sum(r.scene_motion is not None for r in self.rooms.values()),
                "idle_seconds": self.idle_seconds}

    @staticmethod
    def claim_result(number, language):
        result = {"room": number}
        if language in {"fr", "en"}:
            result["voice_language"] = "default"
        return result

    async def claim(self, *, create=False, language="zh"):
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
                    if room is not None and not create and not self.busy(room) \
                            and room.reserved_until <= now:
                        room.reserved_until = now + 15
                        room.last_used = now
                        return {"room": number, "voice_language": language}
            if not create:
                for number, room in self.rooms.items():
                    if number in self.french_rooms or number in self.english_rooms:
                        continue
                    if not self.busy(room) and room.reserved_until <= now:
                        room.reserved_until = now + 15
                        room.last_used = now
                        return self.claim_result(number, language)
            for index in range(1, self.limit + 1):
                number = str(index)
                if number not in self.rooms and number not in self.french_rooms \
                        and number not in self.english_rooms:
                    room = self._make(number)
                    room.reserved_until = now + 15
                    self.rooms[number] = room
                    return self.claim_result(number, language)
            raise HTTPException(409, f"房间已达上限（{self.limit}），可加入已有房间或稍后重试")

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

    async def watch(self):
        while True:
            await asyncio.sleep(15)
            await self.reap()
