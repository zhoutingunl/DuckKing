"""Deterministic, bounded robot adaptations of two folk-dance movement motifs.

These are timed high-level intents, not new learned policies or exact human choreography.
The standing-body command must be inactive while walking: robotd otherwise zeros the twist.
"""

import math
from dataclasses import dataclass

CHOREOGRAPHIES = {"flash_step": "闪身步", "bear_shake": "狗熊哆嗦毛"}
DEFAULT_DURATION = 3.0
MIN_DURATION = 2.4


@dataclass(frozen=True)
class Frame:
    phase: str
    forward: float = 0.0
    lateral: float = 0.0
    turn: float = 0.0
    head_pitch: float = 0.0
    head_yaw: float = 0.0
    head_roll: float = 0.0
    body_z: float = 0.0
    body_roll: float = 0.0
    body_pitch: float = 0.0
    body_active: bool = False


def smooth(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def pulse(value: float) -> float:
    """A short smooth entrance, a held beat, and a smooth exit."""
    return smooth(value / 0.18) * smooth((1 - value) / 0.18)


def sample(name: str, elapsed: float, duration: float = DEFAULT_DURATION) -> Frame:
    if (
        not math.isfinite(elapsed)
        or not math.isfinite(duration)
        or not MIN_DURATION <= duration <= 3
    ):
        raise ValueError("组合动作时长须为 2.4–3 秒，时间必须为有限数值")
    if name not in CHOREOGRAPHIES:
        raise ValueError("未知组合动作")
    u = min(1.0, max(0.0, elapsed / duration))
    if u == 1:
        return Frame("收势")
    if name == "flash_step":
        if u < 0.12:
            amount = pulse(u / 0.12)
            return Frame(
                "预备",
                head_yaw=0.12 * amount,
                body_z=-0.008 * amount,
                body_roll=0.04 * amount,
                body_active=True,
            )
        if u < 0.42:
            amount = pulse((u - 0.12) / 0.30)
            return Frame(
                "左闪",
                forward=0.12 * amount,
                lateral=0.28 * amount,
                turn=0.45 * amount,
                head_yaw=0.22 * amount,
                head_roll=-0.07 * amount,
            )
        if u < 0.76:
            amount = pulse((u - 0.42) / 0.34)
            return Frame(
                "回闪",
                forward=0.08 * amount,
                lateral=-0.28 * amount,
                turn=-0.40 * amount,
                head_yaw=-0.22 * amount,
                head_roll=0.07 * amount,
            )
        amount = pulse((u - 0.76) / 0.24)
        return Frame("收势", head_pitch=0.07 * amount, body_z=-0.004 * amount, body_active=True)
    if u < 0.16:
        amount = smooth(u / 0.16)
        return Frame("轻蹲", body_z=-0.010 * amount, head_pitch=-0.05 * amount, body_active=True)
    if u < 0.84:
        beat = (u - 0.16) / 0.68
        angle = math.tau * 4 * beat
        envelope = pulse(beat)
        wave = math.sin(angle) * envelope
        bounce = 0.5 * (1 - math.cos(2 * angle)) * envelope
        return Frame(
            "抖毛",
            head_pitch=-0.05 + 0.025 * math.sin(2 * angle) * envelope,
            head_yaw=0.20 * wave,
            head_roll=-0.07 * wave,
            body_z=-0.010 - 0.003 * bounce,
            body_roll=0.075 * wave,
            body_pitch=0.025 * wave,
            body_active=True,
        )
    amount = 1 - smooth((u - 0.84) / 0.16)
    return Frame("收势", head_pitch=-0.05 * amount, body_z=-0.010 * amount, body_active=True)
