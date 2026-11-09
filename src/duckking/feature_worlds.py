"""CPU scene adapters. Every adapter owns its model, data and controller history."""

import asyncio
from contextlib import suppress

from .motion import Action, MotionController
from .simulation import MuJoCoBackend


class TaskMuJoCoBackend(MuJoCoBackend):
    """Functional scenes advance only during a task, never on a status read."""

    task_active = False

    def start(self):
        if self.task_active:
            super().start()


class ExistingWorld:
    def __init__(self, assets, capability):
        self.capability = capability
        self.backend = TaskMuJoCoBackend(assets)
        self.backend.load("seated" if capability == "director" else "skills")
        self.motion = MotionController(self.backend)
        self.metrics = {}

    def geometry(self):
        return self.backend.geometry()

    async def snapshot(self):
        return await self.backend.snapshot()

    async def action(self, name, **kwargs):
        self.backend.task_active = True
        action = Action(name=name, **kwargs)
        await self.motion.submit(action)
        result = await self.motion.wait(action.request_id)
        if result["status"] != "completed":
            raise ValueError(result.get("error", "动作未完成"))
        return result.get("outcome", {})

    async def perform(self, command):
        before, _ = self.backend.drivers[0].pose(self.backend.data)
        if self.capability == "director":
            await self.action("seated_ready")
            for member in command.order:
                await self.action("seated_solo", target=member)
        else:
            if command.action in {"sit", "stand"}:
                await self.action(command.action)
            else:
                remaining = command.duration
                while remaining > 0:
                    duration = min(3, remaining)
                    kwargs = {"duration": duration}
                    if command.action in {"walk", "backward"}:
                        kwargs["speed"] = command.speed
                    await self.action(command.action, **kwargs)
                    remaining -= duration
        snapshot = await self.backend.snapshot()
        after, _ = self.backend.drivers[0].pose(self.backend.data)
        self.metrics = {
            "distance_m": float(sum((after - before)[:2] ** 2) ** 0.5),
            "sim_time": snapshot["sim_time"],
        }
        upright = all(not d["fallen"] for d in snapshot["ducks"])
        return {
            "verified": upright,
            "message": "动作已完成" if upright else "身体失稳，未完成动作",
            **self.metrics,
        }

    async def stop(self):
        self.backend.task_active = False
        action = Action(name="stop")
        await self.motion.submit(action)
        await self.motion.wait(action.request_id)
        await self.backend.stop()
        if self.backend.task:
            self.backend.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.backend.task
            self.backend.task = None

    async def reset(self):
        await self.stop()
        self.backend.load(self.backend.scene)
        self.metrics = {}

    async def close(self):
        await self.motion.close()


def make_world(assets, capability):
    if capability in {"movement", "director"}:
        return ExistingWorld(assets, capability)
    if capability in {"hop", "flamingo", "step"}:
        from .feature_policies import PolicyWorld

        return PolicyWorld(assets, capability)
    if capability == "footsteps":
        from .feature_footsteps import FootstepsWorld

        return FootstepsWorld(assets)
    if capability == "swing":
        from .feature_swing import SwingWorld

        return SwingWorld(assets)
    if capability == "dock":
        from .feature_dock import DockWorld

        return DockWorld(assets)
    if capability in {"senses", "theremin", "search", "soccer", "navigation"}:
        from .feature_senses import SensesWorld

        return SensesWorld(assets, capability)
    if capability == "emotions":
        from .feature_emotions import EmotionWorld

        return EmotionWorld(assets)
    if capability == "circus":
        from .feature_circus import CircusWorld

        return CircusWorld(assets)
    raise ValueError("未知功能场景")
