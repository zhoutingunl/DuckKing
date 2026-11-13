"""Official emotion keyframes on the standing/sitting policy, with original WAVs.

Retiming and curious's head correction match Pollen's vendor-emotions.py.
The unsupported play_dead joint-level pose is intentionally not advertised.
"""

import json

import numpy as np

from .feature_policies import PolicyWorld, session

EMOTIONS = (
    "sad",
    "devastated",
    "curious",
    "mmh",
    "yes",
    "yes_fast",
    "no",
    "defiant",
    "angry",
    "mock",
    "excited",
    "impatient",
    "laugh",
)


class EmotionWorld(PolicyWorld):
    def __init__(self, assets):
        super().__init__(assets, "emotions")
        self.sit = session(assets / "policies/alpha_sitstand.onnx")
        self.library = assets / "features/emotions"
        entries = json.loads((self.library / "emotions.json").read_text())["emotions"]
        self.entries = {e["name"]: e for e in entries if e["name"] in EMOTIONS}
        self.seated = False

    async def perform(self, command):
        entry = self.entries[command.action]
        raw = json.loads((self.library / entry["keyframes"]).read_text())["keyframes"]
        start, duration = entry["sound_at_s"], entry["duration_s"]
        frames = [
            dict(f, t=f["t"] - start)
            for f in raw
            if start - 1e-6 <= f["t"] <= start + duration + 1e-6
        ]
        self.metrics = {"emotion": command.action}
        if self.seated:
            self.command[:] = 0
            self.active_policy = self.sit
            await self.advance(3)
            self.seated = False
        self.active_policy = self.walk
        self.command[:] = 0
        self.metrics = {"emotion": command.action, "emotion_elapsed_s": 0}
        times = [f["t"] for f in frames]
        keys = ("neck", "head_pitch", "head_yaw", "head_roll", "body_pitch")
        for k in range(round(duration * 50)):
            elapsed = k / 50
            index = max(0, np.searchsorted(times, elapsed, side="right") - 1)
            frame = frames[index]
            if frame.get("skill") in {"sit", "sit_down"} or command.action == "devastated":
                self.active_policy = self.sit
                self.command[0] = 1
                self.seated = True
            values = [
                float(np.interp(elapsed, times, [f.get(key, 0) for f in frames])) for key in keys
            ]
            if command.action == "curious":
                values[:2] = [0, 0]
            self.command[3:7] = values[:4]
            self.command[11] = values[4]
            self.metrics["emotion_elapsed_s"] = elapsed
            await self.advance(0.02)
        return {"verified": self.upright() > 0.7, "message": "官方情绪关键帧已播放", **self.metrics}

    async def reset(self):
        await super().reset()
        self.seated = False
