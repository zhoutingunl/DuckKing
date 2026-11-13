"""Published terrain-specialist policies on bounded, visible CPU test courses.

These fixed courses are DuckKing tests, not a replay of upstream randomized
batches. Wind is an applied trunk force. Slipperiness is contact friction.
"""

import math

import mujoco
import numpy as np

from .feature_policies import PolicyWorld


class TerrainWorld(PolicyWorld):
    def configure_spec(self, spec):
        if self.capability == "giant_ball":
            ball = spec.worldbody.add_body(name="giant_ball", pos=[0.205, -0.042, 0.15])
            ball.add_freejoint(name="giant_ball_root")
            ball.add_geom(
                name="giant_ball_geom",
                type=mujoco.mjtGeom.mjGEOM_SPHERE,
                size=[0.15, 0, 0],
                mass=0.275,
                group=2,
                rgba=[0.96, 0.68, 0.08, 1],
                condim=6,
                priority=2,
                friction=[0.7, 0.005, 0.002],
            )
            return spec
        if self.capability == "terrain_slip":
            for geom in spec.geoms:
                if "foot_collision" in geom.name:
                    geom.friction = [0.2, 0.005, 0.0001]
                    geom.priority = 2
        if self.capability in {"terrain_rough", "terrain_slope"}:
            rows, cols = 17, 65
            xs = np.linspace(-1, 3, cols)
            if self.capability == "terrain_slope":
                height = np.tile(np.maximum(0, 0.15 - np.abs(xs - 1.5) * 0.1), (rows, 1))
                maximum = 0.15
            else:
                height = np.random.default_rng(7).uniform(0, 0.01, (rows, cols))
                height[:, xs < 0.2] = 0
                maximum = 0.01
            field = spec.add_hfield(
                name="terrain_surface",
                nrow=rows,
                ncol=cols,
                size=[2, 1, maximum, 0.02],
                userdata=(height / maximum).ravel(),
            )
            spec.worldbody.add_geom(
                name="terrain_surface",
                type=mujoco.mjtGeom.mjGEOM_HFIELD,
                hfieldname=field.name,
                pos=[1, 0, 0],
                group=2,
                rgba=[0.56, 0.66, 0.46, 1],
                friction=[1, 0.005, 0.0001],
            )
        if self.capability in {"terrain_step", "terrain_stairs"}:
            count = 3 if self.capability == "terrain_stairs" else 1
            for i in range(count):
                depth = 1.3 if i == 0 else 0.25
                top = (count - i) * 0.025
                spec.worldbody.add_geom(
                    name=f"terrain_step_{i}",
                    type=mujoco.mjtGeom.mjGEOM_BOX,
                    size=[depth * 0.5, 0.6, top * 0.5],
                    pos=[-0.35 if i == 0 else 0.3 + (i - 1) * 0.25 + depth * 0.5, 0, top * 0.5],
                    rgba=[0.58, 0.67, 0.50, 1],
                    group=2,
                    friction=[1, 0.005, 0.0001],
                    solref=[0.04, 1],
                )
        return spec

    def __init__(self, assets, capability):
        self.spawn_height = (
            0.075
            if capability == "terrain_stairs"
            else 0.025
            if capability == "terrain_step"
            else 0
        )
        super().__init__(assets, capability)
        self.contacts = 0
        self.trial_started = False
        if capability == "giant_ball":
            self.substep_observer = self.observe_ball

    def observe_ball(self):
        ball = self.model.geom("giant_ball_geom").id
        right = self.foot_geoms[1]
        self.contacts += sum(
            c.dist < 0.002
            and ((c.geom1 == ball and c.geom2 in right) or (c.geom2 == ball and c.geom1 in right))
            for c in self.data.contact
        )

    async def perform(self, command):
        if getattr(self, "trial_started", False):
            raise ValueError("本轮已结束，请先重置场景再试")
        self.trial_started = True
        self.metrics = {}
        self.active_policy = self.policy
        self.command[:] = 0
        start = self.data.qpos[:2].copy()
        origin = self.data.time
        self.contacts = 0
        ball_start = (
            self.data.xpos[self.model.body("giant_ball").id].copy()
            if self.capability == "giant_ball"
            else None
        )
        seconds = 5 if ball_start is not None else 14 if self.capability == "terrain_gale" else 10
        try:
            for _ in range(seconds * 50):
                elapsed = self.data.time - origin
                if ball_start is None:
                    self.command[0] = 0.3
                elif elapsed >= 1:
                    self.active_policy = self.walk
                if self.capability == "terrain_gale":
                    force = min(3, elapsed / 12 * 3)
                    self.data.xfrc_applied[self.body, :3] = (
                        -self.data.xmat[self.body].reshape(3, 3)[:, 0] * force
                    )
                    self.metrics["wind_force_n"] = force
                await self.advance(0.02, allow_head_support=True)
                self.metrics.update(
                    distance_m=float(np.linalg.norm(self.data.qpos[:2] - start)),
                    forward_progress_m=float(self.data.qpos[0] - start[0]),
                    upright=self.upright(),
                    foot_friction=0.2 if self.capability == "terrain_slip" else 1.0,
                )
                if ball_start is not None:
                    ball_pos = self.data.xpos[self.model.body("giant_ball").id]
                    self.metrics.update(
                        ball_travel_m=float(np.linalg.norm((ball_pos - ball_start)[:2])),
                        foot_ball_contacts=self.contacts,
                    )
                if self.upright() < math.cos(math.radians(60)):
                    return {"verified": False, "message": "身体失稳，已暂停物理", **self.metrics}
        finally:
            self.data.xfrc_applied[:] = 0
            self.command[:] = 0
        passed = self.metrics["forward_progress_m"] >= 0.2
        if self.capability in {"terrain_step", "terrain_stairs"}:
            edge = 0.8 if self.capability == "terrain_stairs" else 0.3
            passed = self.data.qpos[0] > edge + 0.1 and self.data.qpos[2] < 0.15
        if ball_start is not None:
            passed = self.contacts > 0 and ball_pos[0] - ball_start[0] > 0.1
        return {
            "verified": bool(passed),
            "message": "按本轮实际运动、接触和姿态验收",
            **self.metrics,
        }

    async def reset(self):
        self.trial_started = False
        await super().reset()
        self.contacts = 0

    async def snapshot(self):
        state = await super().snapshot()
        state["view_scene"] = "terrain"
        state["camera_follow"] = state["ducks"][0]["position"]
        if self.capability == "giant_ball":
            ball = self.data.xpos[self.model.body("giant_ball").id]
            duck = self.data.xpos[self.body]
            state["camera_follow"] = ((ball + duck) * 0.5).tolist()
            state["camera_radius_m"] = float(np.linalg.norm((ball - duck)[:2])) * 0.5 + 0.2
        return state
