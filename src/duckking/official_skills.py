"""Measured, time-bounded official one-shots and passive-wheel skating."""

import asyncio
import math
import time

import numpy as np

from .idle import yawn_frame

HOLD = {"roulade": 2, "ground_pick": 2.8, "roller_crouch": 3.5, "skate": 3, "yawn": 4}


class SkillRun:
    def __init__(self, backend, name):
        self.b, self.name = backend, name
        self.driver = backend.drivers[0]
        self.start = float(backend.data.time)
        self.origin = self.driver.pose(backend.data)[0].copy()
        self.start_mouth = float(backend.data.site_xpos[backend.model.site("mouth_tip").id, 2])
        self.wheels = [
            backend.model.jnt_qposadr[j]
            for j in range(backend.model.njnt)
            if (backend.model.joint(j).name or "").startswith("passive_")
        ]
        self.wheel_start = backend.data.qpos[self.wheels].copy()
        self.last_angle = self.angle = 0.0
        self.rotation_min = self.rotation_max = 0.0
        self.min_upright = 1.0
        self.min_mouth = self.start_mouth
        self.min_height = float(self.origin[2])
        self.max_mouth = self.max_displacement = self.wheel_rotation = 0.0
        self.supported = False
        self.stable_s = 0.0
        self.status = "running"

    def tick(self):
        b, d = self.b, self.driver
        if self.status != "running":
            return
        elapsed = float(b.data.time) - self.start
        if self.name == "yawn":
            pitch, mouth = yawn_frame(elapsed)
            d.command[4] = pitch
            b.data.ctrl[b.idle.mouth] = mouth
            self.max_mouth = max(
                self.max_mouth, float(b.data.qpos[b.model.jnt_qposadr[b.model.joint("mouth").id]])
            )
        if self.name == "skate" and elapsed >= HOLD[self.name]:
            d.command[:] = 0
        rot = b.data.xmat[d.body].reshape(3, 3)
        angle = math.atan2(-rot[2, 0], rot[2, 2])
        delta = angle - self.last_angle
        self.angle += math.atan2(math.sin(delta), math.cos(delta))
        self.last_angle = angle
        self.rotation_min = min(self.rotation_min, self.angle)
        self.rotation_max = max(self.rotation_max, self.angle)
        self.min_upright = min(self.min_upright, float(rot[2, 2]))
        self.min_mouth = min(
            self.min_mouth, float(b.data.site_xpos[b.model.site("mouth_tip").id, 2])
        )
        self.min_height = min(self.min_height, float(b.data.qpos[d.root + 2]))
        self.max_displacement = max(
            self.max_displacement, float(np.linalg.norm(d.pose(b.data)[0][:2] - self.origin[:2]))
        )
        if self.wheels:
            self.wheel_rotation = max(
                self.wheel_rotation,
                float(np.max(np.abs(b.data.qpos[self.wheels] - self.wheel_start))),
            )
        floor = b.model.geom("floor").id
        self.supported = any(
            (int(c.geom1) == floor and int(c.geom2) in d.contact_geoms)
            or (int(c.geom2) == floor and int(c.geom1) in d.contact_geoms)
            for c in b.data.contact
        )
        height_min = 0.045 if self.name == "yawn" and d.rest_posture == "sit" else 0.10
        upright = rot[2, 2] > 0.94 and b.data.qpos[d.root + 2] > height_min
        root_v = b.model.jnt_dofadr[b.model.joint("trunk_base_freejoint").id]
        slow = np.linalg.norm(b.data.qvel[root_v : root_v + 3]) < 0.08
        self.stable_s = self.stable_s + 0.02 if upright and slow and self.supported else 0

    def snapshot(self):
        return {
            "name": self.name,
            "status": self.status,
            "source": "local_choreography" if self.name == "yawn" else "official_onnx_measured",
            "rotation_rad": self.rotation_max - self.rotation_min,
            "min_upright": self.min_upright,
            "min_mouth_height_m": self.min_mouth,
            "min_body_height_m": self.min_height,
            "max_mouth_open_rad": self.max_mouth,
            "displacement_m": self.max_displacement,
            "wheel_rotation_rad": self.wheel_rotation,
            "supported": self.supported,
            "stable_s": self.stable_s,
        }

    def verified(self):
        measurements = {
            "roulade": self.min_upright < -0.5 and self.rotation_max - self.rotation_min > 5,
            "ground_pick": self.min_mouth < 0.04 and self.start_mouth - self.min_mouth > 0.12,
            "skate": self.max_displacement > 0.05 and self.wheel_rotation > 1,
            "roller_crouch": self.origin[2] - self.min_height > 0.035,
            "yawn": self.max_mouth > 0.20,
        }
        return bool(measurements[self.name] and self.stable_s >= 0.3)


async def perform_skill(backend, action):
    name = action.name
    expected = "rollers" if name in {"skate", "roller_crouch"} else "skills"
    if backend.scene != expected or action.target != "a":
        raise ValueError("请先切换到轮滑场景" if expected == "rollers" else "请先切换到动作练习场")
    if name in {"idle_on", "idle_off"}:
        backend.idle.enabled = name == "idle_on"
        return {
            "verified": True,
            "idle_enabled": backend.idle.enabled,
            "source": "local_choreography_official_inspired",
        }
    driver = backend.drivers[0]
    if backend.data.xmat[driver.body, 8] < 0.94:
        raise ValueError("小鸭尚未站稳，请等待恢复或重置后再试")
    run = backend.skill_run = SkillRun(backend, name)
    driver.command[:] = 0
    if name in {"roulade", "ground_pick", "roller_crouch"}:
        driver.policy = name
        driver.phase_started = float(backend.data.time)
        driver.until = driver.phase_started + HOLD[name]
    if name == "skate":
        driver.command[0] = 0.35
    deadline = time.monotonic() + action.duration + 3
    try:
        while backend.data.time - run.start < action.duration:
            backend.ensure_running()
            if time.monotonic() > deadline:
                raise ValueError("仿真推进超时，动作已停止")
            if run.max_displacement > 1.2:
                raise ValueError("动作偏离练习范围，已停止")
            await asyncio.sleep(0.02)
        verified = run.verified()
        run.status = "completed" if verified else "failed"
        return {
            **run.snapshot(),
            "verified": verified,
            "message": "已确认实际动作与恢复站稳"
            if verified
            else "未确认完整动作或恢复站稳，请重置后重试",
            "object_grasped": False,
        }
    finally:
        if run.status == "running":
            run.status = "interrupted"


async def perform_translation(backend, action):
    drivers = backend.targets()
    starts = [d.pose(backend.data) for d in drivers]
    backward = action.name == "backward"
    speed = action.speed if action.speed is not None else (0.35 if backward else 0.30)
    # The published velstand network has a dead zone at small reverse/lateral
    # commands. Keep the explicit caller's speed, but verify actual displacement.
    lateral = -speed if action.name == "strafe_right" else speed
    for driver in drivers:
        driver.command[:3] = [-speed, 0, 0] if backward else [0, lateral, 0]
    await backend.wait_sim(action.duration)
    measured = []
    for driver, (start, yaw) in zip(drivers, starts, strict=True):
        direction = (
            np.array([-math.cos(yaw), -math.sin(yaw)])
            if backward
            else np.array([-math.sin(yaw), math.cos(yaw)]) * (-1 if lateral < 0 else 1)
        )
        delta = driver.pose(backend.data)[0][:2] - start[:2]
        measured.append(
            {
                "distance_in_direction_m": float(np.dot(delta, direction)),
                "upright": float(backend.data.xmat[driver.body, 8]),
            }
        )
    verified = all(m["distance_in_direction_m"] > 0.005 and m["upright"] > 0.90 for m in measured)
    return {
        "verified": verified,
        "ducks": measured,
        "source": "official_velstand_measured",
        "message": "已确认指定方向的实际位移"
        if verified
        else "未确认指定方向的位移，请增加时长、调整速度或重置后重试",
    }
