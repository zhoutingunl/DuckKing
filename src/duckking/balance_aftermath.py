"""Bounded live physics after a scored failure; never part of PPO evaluation.

Keep the last joint targets and brake the disc. Gravity and contacts determine
whether the robot falls to the floor or remains on the disc; do not push it off.
"""

import mujoco
import numpy as np

from .balance import DT

MAX_SECONDS = 4.0


class BalanceAftermath:
    def __init__(self, world):
        self.world = world
        self.started = float(world.data.time)
        self.seconds = 0.0
        self.active = True
        self.reason = None
        self.ground_contact = False
        self.rest_seconds = 0.0
        self.measured = world.measure()
        self._observe_ground()

    def _observe_ground(self):
        world = self.world
        self.ground_contact |= any(
            world.floor in (contact.geom1, contact.geom2)
            and bool({int(contact.geom1), int(contact.geom2)} & world.driver.contact_geoms)
            for contact in world.data.contact
        )

    def finish(self, reason):
        self.active = False
        self.reason = reason

    def step(self):
        if not self.active:
            return
        world = self.world
        before = float(world.data.time)
        rate = np.array([0.12, 0.12, 1.2]) * world.model.opt.timestep
        # No new task/gait inference, score updates, forces or pose assignments.
        for _ in range(round(DT / world.model.opt.timestep)):
            world.target += np.clip(-world.target, -rate, rate)
            world.data.ctrl[world.disc_act] = world.target
            mujoco.mj_step(world.model, world.data)
            self._observe_ground()
        mujoco.mj_forward(world.model, world.data)
        if (not np.isfinite(world.data.qpos).all()
                or not np.isfinite(world.data.qvel).all()
                or abs(float(world.data.time) - before - DT) > 1e-7):
            raise FloatingPointError("跌落过程物理状态或时钟异常，已暂停")
        self.seconds = round(float(world.data.time) - self.started, 6)
        self.measured = world.measure()
        velocity = np.zeros(6)
        mujoco.mj_objectVelocity(
            world.model, world.data, mujoco.mjtObj.mjOBJ_XBODY, world.driver.body, velocity, 0
        )
        resting = self.ground_contact and np.linalg.norm(velocity) < 0.5
        self.rest_seconds = self.rest_seconds + DT if resting else 0.0
        if self.rest_seconds >= 0.5 and abs(self.measured["rpm"]) < 0.25:
            self.finish("landed")
        elif self.seconds >= MAX_SECONDS:
            self.finish("time_limit")

    def snapshot(self):
        return {
            "phase": "running" if self.active else "finished",
            "seconds": self.seconds,
            "max_seconds": MAX_SECONDS,
            "ground_contact": self.ground_contact,
            "reason": self.reason,
            "measurements": self.measured,
            "counts_toward_score": False,
        }
