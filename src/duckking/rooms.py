"""Bounded public demo rooms; identities persist privately, live state does not."""

import asyncio
import time
from types import SimpleNamespace

from fastapi import HTTPException

from .diagnostics import VoiceDiagnostics
from .motion import MotionController, PreviewBackend


class RoomRegistry:
    def __init__(self, primary):
        self.primary = primary
        self.limit = primary.settings.max_rooms if primary.motion.backend.kind == "preview" else 1
        self.physics_limit = min(self.limit, primary.settings.max_physics_rooms)
        self.idle_seconds = primary.settings.room_idle_seconds
        self.lock = asyncio.Lock()
        primary.last_used = time.monotonic()
        self.rooms = {"1": primary}
        if self.limit >= 2:
            self.rooms["2"] = self._make("2")

    def _make(self, number):
        settings = self.primary.settings.for_room(number)
        return SimpleNamespace(
            motion=MotionController(PreviewBackend()), voice=None, scene_motion=None,
            settings=settings, scene_lock=asyncio.Lock(), viewers=0, reserved_until=0.0,
            last_used=time.monotonic(), voice_diagnostics=VoiceDiagnostics(
                settings.data_dir / "voice.jsonl"
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
        return (room.viewers or room.voice is not None or room.motion.current is not None
                or (room.scene_motion is not None and (room.scene_motion.current is not None
                    or (room.scene_motion.studio is not None
                        and room.scene_motion.studio.task is not None
                        and not room.scene_motion.studio.task.done()))))

    def snapshot(self):
        return {"rooms": [{"id": number, "viewers": room.viewers,
                           "voice_busy": room.voice is not None,
                           "physics": room.scene_motion is not None}
                          for number, room in self.rooms.items()],
                "capacity": self.limit, "physics_capacity": self.physics_limit,
                "physics_active": sum(r.scene_motion is not None for r in self.rooms.values()),
                "idle_seconds": self.idle_seconds}

    async def claim(self, *, create=False):
        await self.reap()
        async with self.lock:
            now = time.monotonic()
            if not create:
                for number, room in self.rooms.items():
                    if not self.busy(room) and room.reserved_until <= now:
                        room.reserved_until = now + 15
                        room.last_used = now
                        return {"room": number}
            for index in range(1, self.limit + 1):
                number = str(index)
                if number not in self.rooms:
                    room = self._make(number)
                    room.reserved_until = now + 15
                    self.rooms[number] = room
                    return {"room": number}
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
                    if number not in {"1", "2"}:
                        del self.rooms[number]
                        await room.motion.close()
                    if room.scene_motion:
                        controller, room.scene_motion = room.scene_motion, None
                        await controller.close()

    async def watch(self):
        while True:
            await asyncio.sleep(15)
            await self.reap()
