"""Audience-facing goals; keep the recorded training contract and rewards intact."""

import math

VERSION = "balance-demo-v1"
CENTER_RADIUS = 0.08
CENTER_HOLD = 1.0
HEADING_FRACTION = 0.85


def goal(level):
    task = {
        1: "全程站稳，允许随盘转动，不要求回中心。",
        2: "全程站稳，至少85%的控制步朝向误差小于25°，不要求回中心。",
        3: "全程站稳，结束时躯干投影在盘心8 cm内，并已连续保持至少1秒；不要求固定朝向。",
    }[level]
    return {
        "version": VERSION,
        "description": (task + "完整运行设定时长，结尾盘速小于0.25 RPM、两倾角均小于1°；"
                        "手动停止不计成功。"),
        "center_radius_m": CENTER_RADIUS if level == 3 else None,
        "center_hold_seconds": CENTER_HOLD if level == 3 else None,
        "heading_fraction": HEADING_FRACTION if level == 2 else None,
    }


def evaluate(info, *, level, duration, done, cancelled=False):
    """Grade measured physics, never modify its termination, reward or policy."""
    def finite(key):
        value = info.get(key)
        return value if isinstance(value, (int, float)) and math.isfinite(value) else None

    seconds = finite("seconds")
    checks = {
        "duration": seconds is not None and seconds >= duration - 1e-6,
        "safe": info["reason"] != "fell_or_left_disc",
        "uninterrupted": not cancelled and info["reason"] != "cancelled",
        "disk_stopped": info.get("disk_stopped") is True,
    }
    if level == 2:
        heading = finite("heading_fraction")
        checks["heading"] = heading is not None and heading >= HEADING_FRACTION
    if level == 3:
        radius, hold = finite("radius"), finite("center_hold")
        checks["center"] = radius is not None and radius < CENTER_RADIUS
        # Ten 0.1-second control ticks can sum to 0.9999999999999999.
        checks["center_hold"] = hold is not None and hold >= CENTER_HOLD - 1e-6
    success = bool(done and all(checks.values()))
    reason = (
        "fell_or_left_disc" if not checks["safe"] else
        "cancelled" if not checks["uninterrupted"] else
        "success" if success else "criteria_not_met" if done else None
    )
    return {
        **info,
        "success": success,
        "reason": reason,
        "acceptance": {"version": VERSION, "checks": checks},
        "training_evaluation": {
            "contract": "balance-v4-gain-bodyframe",
            "success": info["success"],
            "reason": info["reason"],
        },
    }
