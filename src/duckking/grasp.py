"""Bounded beak manipulation, verified from contact forces and free-body motion."""

import asyncio
import time

import mujoco
import numpy as np

from .grasp_model import MOUTH_CLOSED, MOUTH_OPEN


class BeakGrasp:
    def __init__(self, backend):
        self.backend = backend
        self.model, self.data = backend.model, backend.data
        self.driver = backend.drivers[0]
        self.mouth = self.model.actuator("mouth").id
        self.mouth_q = self.model.jnt_qposadr[self.model.joint("mouth").id]
        self.object = self.model.body("carry_object").id
        self.object_geom = self.model.geom("object_geom").id
        self.object_v = self.model.jnt_dofadr[self.model.joint("object_free").id]
        self.head = self.model.body("jaw_soft").id
        self.data.qpos[self.mouth_q] = self.data.ctrl[self.mouth] = MOUTH_OPEN
        self.phase = "ready"
        self.held = self.carried = False
        self.failure = None
        self.forces = dict(upper=0.0, lower=0.0, source=0.0, destination=0.0, floor=0.0)
        self.contact_samples = dict(upper=0, lower=0)
        self.bilateral_s = self.max_bilateral_s = self.loss_s = self.released_s = 0.0
        self.peak_force = self.max_lift = self.max_slip = 0.0
        self.start = np.array([0.062, -0.002, 0.208])
        self.grip_relative = None
        self.carry_distance = self.robot_distance = 0.0

    def position(self):
        return self.data.xpos[self.object].copy()

    def relative(self):
        return self.data.xmat[self.head].reshape(3, 3).T @ (
            self.position() - self.data.xpos[self.head]
        )

    def clearance(self):
        # Lowest corner of the oriented box relative to the source support plane.
        extent = (
            np.abs(self.data.geom_xmat[self.object_geom].reshape(3, 3)[2])
            @ (self.model.geom_size[self.object_geom])
        )
        return float(self.position()[2] - extent - 0.204)

    def update(self):
        forces = dict.fromkeys(self.forces, 0.0)
        force = np.zeros(6)
        for i, contact in enumerate(self.data.contact):
            if self.object_geom not in (contact.geom1, contact.geom2):
                continue
            other = contact.geom2 if contact.geom1 == self.object_geom else contact.geom1
            name = self.model.geom(other).name
            key = (
                "upper"
                if name == "upper_pad"
                else "lower"
                if name == "lower_pad"
                else "source"
                if name.startswith("source_")
                else "destination"
                if name == "destination_support"
                else "floor"
                if name == "floor"
                else None
            )
            if key:
                mujoco.mj_contactForce(self.model, self.data, i, force)
                forces[key] += max(0.0, float(force[0]))
        self.forces = forces
        dt = self.model.opt.timestep
        bilateral = min(forces["upper"], forces["lower"]) > 0.01
        self.bilateral_s = self.bilateral_s + dt if bilateral else 0.0
        self.max_bilateral_s = max(self.max_bilateral_s, self.bilateral_s)
        self.loss_s = 0.0 if bilateral else self.loss_s + dt
        self.peak_force = max(self.peak_force, forces["upper"], forces["lower"])
        for key in self.contact_samples:
            self.contact_samples[key] += int(forces[key] > 0.01)
        if bilateral:
            self.max_lift = max(self.max_lift, self.clearance())
        released = (
            forces["destination"] > 0.005
            and forces["upper"] + forces["lower"] < 0.001
            and np.linalg.norm(self.data.qvel[self.object_v : self.object_v + 3]) < 0.02
            and np.linalg.norm(self.data.qvel[self.object_v + 3 : self.object_v + 6]) < 0.1
        )
        self.released_s = self.released_s + dt if released else 0.0
        if self.held and self.phase not in {"opening", "retreating", "released"}:
            slip = float(np.linalg.norm(self.relative() - self.grip_relative))
            self.max_slip = max(self.max_slip, slip)
            fallen = self.data.xmat[self.driver.body].reshape(3, 3)[2, 2] < 0.45
            if self.loss_s > 0.12 or slip > 0.018 or fallen:
                self.failure = "夹持已丢失或小鸭失去平衡，请重置场景后重试"
                self.phase, self.held = "dropped", False
                self.driver.command[:3] = 0

    def check(self):
        self.backend.ensure_running()
        if self.failure:
            raise ValueError(self.failure)
        if self.data.xmat[self.driver.body].reshape(3, 3)[2, 2] < 0.45:
            raise ValueError("小鸭失去平衡，请重置场景")

    async def ramp(self, duration, update=lambda _: None):
        start = self.data.time
        deadline = time.monotonic() + duration + 3
        while self.data.time - start < duration:
            self.check()
            if time.monotonic() > min(deadline, self.deadline):
                raise ValueError("夹取动作推进超时，已停止")
            update(min(1.0, (self.data.time - start) / duration))
            await asyncio.sleep(0.02)
        update(1.0)
        self.check()

    def stop(self):
        # Stop translation immediately. A secured object stays clamped; opening is explicit.
        if self.phase in {"closing", "lifting", "carrying", "lowering", "opening", "retreating"}:
            self.phase = "interrupted"
            if not self.held:
                self.data.ctrl[self.mouth] = self.data.qpos[self.mouth_q]

    async def perform(self, name):
        self.check()
        self.deadline = time.monotonic() + ({"pick_up": 2.2, "carry": 3, "put_down": 4.5}[name]) + 3
        try:
            if name == "pick_up":
                if self.phase != "ready" or self.held:
                    raise ValueError("请重置到取物位置后再夹起")
                if (
                    self.forces["source"] < 0.005
                    or np.linalg.norm(self.position() - self.start) > 0.025
                ):
                    raise ValueError("物品不在取物架上，无法夹取；请重置场景")
                self.phase = "closing"
                await self.ramp(
                    1.0,
                    lambda t: self.data.ctrl.__setitem__(
                        self.mouth, MOUTH_OPEN + (MOUTH_CLOSED - MOUTH_OPEN) * t
                    ),
                )
                self.phase = "lifting"
                await self.ramp(0.8, lambda t: self.driver.command.__setitem__(4, -0.6 * t))
                await self.ramp(0.4)
                verified = (
                    self.bilateral_s >= 0.2
                    and self.clearance() > 0.008
                    and self.forces["source"] < 0.001
                )
                if verified:
                    self.held = True
                    self.grip_relative = self.relative()
                    self.phase = "holding"
                message = (
                    "已验证双侧接触、持续夹持和物品离架"
                    if verified
                    else "未形成稳定夹持或物品未离架"
                )
            elif name == "carry":
                if not self.held or self.carried or self.phase != "holding":
                    raise ValueError("请先成功夹起物品，再执行一次搬运")
                self.phase = "carrying"
                obj, robot = self.position(), self.driver.pose(self.data)[0]
                # The official policy gates head pose to standing. Clear it for walking.
                self.driver.command[:] = 0
                self.driver.command[0] = 0.25
                await self.ramp(2.8)
                self.driver.command[:3] = 0
                await self.ramp(0.2)
                self.carry_distance = float(np.linalg.norm(self.position()[:2] - obj[:2]))
                self.robot_distance = float(
                    np.linalg.norm(self.driver.pose(self.data)[0][:2] - robot[:2])
                )
                x, y, _ = self.position()
                verified = (
                    self.held
                    and self.bilateral_s >= 0.2
                    and self.carry_distance > 0.10
                    and self.robot_distance > 0.08
                    and 0.24 < x < 0.35
                    and abs(y) < 0.11
                )
                self.carried = bool(verified)
                self.phase = "carried" if verified else "failed"
                message = "已夹持搬运到接物台上方" if verified else "未到达接物台上方，请重置后重试"
            elif name == "put_down":
                if not self.held or not self.carried or self.phase != "carried":
                    raise ValueError("请先夹起并搬运到接物台，再放下")
                self.phase = "opening"
                self.held = False
                initial = float(self.data.ctrl[self.mouth])
                await self.ramp(
                    0.6,
                    lambda t: self.data.ctrl.__setitem__(
                        self.mouth, initial + (MOUTH_OPEN - initial) * t
                    ),
                )
                await self.ramp(1.0, lambda t: self.driver.command.__setitem__(4, 0.5 * t))
                await self.ramp(0.8)
                if self.forces["destination"] < 0.005:
                    raise ValueError("物品尚未接触接物台，停止退开；请重置场景")
                self.held = False
                self.phase = "retreating"
                self.driver.command[:] = 0
                self.driver.command[0] = -0.4
                await self.ramp(0.7)
                self.driver.command[:3] = 0
                await self.ramp(1.4)
                verified = self.released_s >= 0.2
                self.phase = "released" if verified else "failed"
                message = (
                    "已脱离嘴部并在接物台稳定落下"
                    if verified
                    else "尚未确认完全脱离嘴部并落稳，请重置后重试"
                )
            else:
                raise ValueError("不支持的夹取动作")
        except ValueError as exc:
            if self.phase not in {"ready", "holding", "carried", "released", "dropped"}:
                self.phase = "failed"
            return {**self.snapshot(), "verified": False, "message": str(exc)}
        if not verified:
            self.phase = "failed"
        return {**self.snapshot(), "verified": bool(verified), "message": message}

    def snapshot(self):
        return {
            "phase": self.phase,
            "held": self.held,
            "carried": self.carried,
            "position": self.position().tolist(),
            "mouth_angle_deg": float(np.degrees(self.data.qpos[self.mouth_q])),
            "normal_force_n": dict(self.forces),
            "contact_samples": dict(self.contact_samples),
            "bilateral_s": self.bilateral_s,
            "max_bilateral_s": self.max_bilateral_s,
            "peak_normal_force_n": self.peak_force,
            "lift_clearance_m": self.clearance(),
            "max_lift_clearance_m": self.max_lift,
            "carry_distance_m": self.carry_distance,
            "robot_distance_m": self.robot_distance,
            "max_slip_m": self.max_slip,
            "released_stable_s": self.released_s,
            "linear_speed_mps": float(
                np.linalg.norm(self.data.qvel[self.object_v : self.object_v + 3])
            ),
            "angular_speed_radps": float(
                np.linalg.norm(self.data.qvel[self.object_v + 3 : self.object_v + 6])
            ),
            "error": self.failure,
            "model": "experimental_beak_contact_v1",
        }
