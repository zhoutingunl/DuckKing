"""Original bounded games using the installed, licensed generic Pollen policies.

These are DuckKing games inspired by the public challenge rules. They are not
an Arena runner port, do not use its separate reference weights and never report
an official leaderboard score. The lanes, light schedule and rope are physical.
"""

import asyncio
import math
import time

import mujoco
import numpy as np

from .feature_policies import session
from .model_assets import geometry
from .simulation import HOME, Driver


class GameWorld:
    def __init__(self, assets, capability):
        self.capability = capability
        robot = assets / "microduck_rl/src/mjlab_microduck/robot/microduck"
        roller = capability == "roller_race"
        spec = mujoco.MjSpec.from_string("<mujoco><worldbody/></mujoco>")
        self.length = 6 if capability == "red_light" else 1.5 if capability == "hill_race" else 2
        self.slope = math.radians(8) if capability == "hill_race" else 0
        names = ["a_", "b_"] if capability == "tug" else [""]
        for prefix in names:
            rig = mujoco.MjSpec.from_file(
                str(
                    robot
                    / ("robot_groundcontact_rollers.xml" if roller else "robot_allcollisions.xml")
                )
            )
            spec.attach(rig, prefix=prefix, frame=spec.worldbody.add_frame())
        if capability == "tug":
            spec.worldbody.add_geom(
                name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, pos=[0, 0, -0.6], size=[0, 0, 0.01]
            )
            for sign in [-1, 1]:
                spec.worldbody.add_geom(
                    name=f"platform_{sign}",
                    type=mujoco.mjtGeom.mjGEOM_BOX,
                    pos=[sign, 0, -0.05],
                    size=[0.75, 0.45, 0.05],
                    rgba=[0.6, 0.67, 0.49, 1],
                    group=2,
                )
            # Sixteen small links make a rope: ball joints bend freely; the
            # endpoint connects to B's neck, without a rigid duck-to-duck weld.
            parent = (
                spec.body("a_neck_pitch")
                if any(b.name == "a_neck_pitch" for b in spec.bodies)
                else spec.body("a_neck")
            )
            bneck = (
                spec.body("b_neck_pitch")
                if any(b.name == "b_neck_pitch" for b in spec.bodies)
                else spec.body("b_neck")
            )
            self.anchor_b_name = bneck.name
            bneck.add_site(name="rope_b", pos=[0, 0, 0.02], size=[0.001, 0, 0])
            for i in range(16):
                parent = parent.add_body(
                    name=f"rope_{i}", pos=[0, 0, 0.02] if i == 0 else [0.0625, 0, 0]
                )
                if i:
                    parent.add_joint(type=mujoco.mjtJoint.mjJNT_BALL, damping=0.0001)
                parent.add_geom(
                    name=f"rope_geom_{i}",
                    type=mujoco.mjtGeom.mjGEOM_CAPSULE,
                    fromto=[0, 0, 0, 0.0625, 0, 0],
                    size=[0.0025, 0, 0],
                    mass=0.001,
                    rgba=[0.85, 0.3, 0.12, 1] if i == 8 else [0.74, 0.61, 0.32, 1],
                    group=2,
                )
            parent.add_site(name="rope_end", pos=[0.0625, 0, 0], size=[0.001, 0, 0])
            eq = spec.add_equality(
                name="rope_connection",
                type=mujoco.mjtEq.mjEQ_CONNECT,
                name1="rope_end",
                name2="rope_b",
                objtype=mujoco.mjtObj.mjOBJ_SITE,
            )
            eq.solref = [0.01, 1]
        else:
            spec.worldbody.add_geom(
                name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[0, 0, 0.01]
            )
            if self.slope:
                half = (self.length + 0.2) * 0.5
                spec.worldbody.add_geom(
                    name="ramp",
                    type=mujoco.mjtGeom.mjGEOM_BOX,
                    pos=[self.length * 0.5, 0, self.length * 0.5 * math.tan(self.slope) - 0.02],
                    size=[half, 0.4, 0.02],
                    quat=[math.cos(self.slope / 2), 0, -math.sin(self.slope / 2), 0],
                    rgba=[0.6, 0.68, 0.46, 1],
                    group=2,
                    friction=[1, 0.005, 0.0001],
                )
            for sign in [-1, 1]:
                spec.worldbody.add_geom(
                    name=f"lane_{sign}",
                    type=mujoco.mjtGeom.mjGEOM_BOX,
                    pos=[self.length * 0.5, sign * 0.43, 0.025],
                    size=[self.length * 0.5 + 0.15, 0.02, 0.025],
                    rgba=[0.55, 0.64, 0.43, 1],
                    group=2,
                )
            spec.worldbody.add_geom(
                name="finish",
                type=mujoco.mjtGeom.mjGEOM_BOX,
                pos=[self.length, 0, self.length * math.tan(self.slope) + 0.002],
                size=[0.006, 0.4, 0.002],
                rgba=[0.9, 0.2, 0.12, 1],
                group=2,
                contype=0,
                conaffinity=0,
            )
            if capability == "red_light":
                spec.worldbody.add_geom(
                    name="traffic_green",
                    type=mujoco.mjtGeom.mjGEOM_SPHERE,
                    pos=[self.length + 0.1, 0, 0.45],
                    size=[0.1, 0, 0],
                    rgba=[0.2, 0.85, 0.2, 1],
                    group=2,
                    contype=0,
                    conaffinity=0,
                )
        if capability == "red_light":
            spec.worldbody.add_geom(
                name="traffic_red",
                type=mujoco.mjtGeom.mjGEOM_SPHERE,
                pos=[self.length + 0.1, 0, -0.4],
                size=[0.1, 0, 0],
                rgba=[0.95, 0.1, 0.06, 1],
                group=2,
                contype=0,
                conaffinity=0,
            )
        self.model = spec.compile()
        self.model.opt.timestep = 0.005
        for j in range(self.model.njnt):
            if (self.model.joint(j).name or "").startswith("passive_"):
                self.model.dof_frictionloss[self.model.jnt_dofadr[j]] = 0.003
        self.data = mujoco.MjData(self.model)
        self.sessions = {"walk": session(assets / "policies/velstand.onnx")}
        if roller:
            self.sessions["roller"] = session(assets / "policies/roller.onnx")
        self.drivers = [
            Driver(self.model, p, self.sessions, "roller" if roller else "walk") for p in names
        ]
        self.geom_ids = [i for i in range(self.model.ngeom) if self.model.geom_group[i] == 2]
        self.visual = geometry(self.model, self.geom_ids)
        self.metrics = {}
        self.reset_state()

    def reset_state(self):
        mujoco.mj_resetData(self.model, self.data)
        self.trial_started = False
        self.red = False
        if self.capability == "red_light":
            self.model.geom_pos[self.model.geom("traffic_green").id, 2] = 0.45
            self.model.geom_pos[self.model.geom("traffic_red").id, 2] = -0.4
        for i, d in enumerate(self.drivers):
            x = (-0.5 if i == 0 else 0.5) if self.capability == "tug" else 0
            quat = [1, 0, 0, 0] if i == 0 else [0, 0, 0, 1]
            if self.slope:
                quat = [math.cos(self.slope / 2), 0, -math.sin(self.slope / 2), 0]
            self.data.qpos[d.root : d.root + 7] = [
                x,
                0,
                0.1385 if d.base_policy == "roller" else 0.125,
                *quat,
            ]
            self.data.qpos[d.q] = HOME
            self.data.ctrl[d.ids] = HOME
            d.last[:] = 0
            d.command[:] = 0
        mujoco.mj_forward(self.model, self.data)
        if self.capability == "tug":
            body = self.model.body("rope_0").id
            parent = self.model.body_parentid[body]
            q = np.empty(4)
            mujoco.mju_mat2Quat(q, self.data.xmat[parent].reshape(3, 3).T.ravel())
            self.model.body_quat[body] = q
            mujoco.mj_forward(self.model, self.data)
        for _ in range(50):
            self.tick()
        self.metrics = {}

    def tick(self):
        for d in self.drivers:
            d.step(self.model, self.data)
        for _ in range(4):
            before = self.data.time
            mujoco.mj_step(self.model, self.data)
            if self.data.time <= before:
                raise ValueError("物理数值异常，已暂停；请重新准备场景。")
        if not np.isfinite(self.data.qpos).all():
            raise ValueError("物理数值异常，已暂停；请重新准备场景。")

    async def perform(self, command):
        if self.trial_started:
            raise ValueError("本轮已结束；再次点击动作会自动重置起点。")
        self.trial_started = True
        start = self.data.time
        deadline = time.monotonic()
        fallen = 0
        limit = 45 if self.capability == "tug" else 40 if self.capability == "red_light" else 25
        red_origin = None
        reds = 0
        previous_red = False
        watch_start = 0
        for _ in range(limit * 50):
            elapsed = self.data.time - start
            for d in self.drivers:
                d.command[:] = 0
            if self.capability == "tug":
                for d in self.drivers:
                    d.command[0] = -0.16
            else:
                d = self.drivers[0]
                p, yaw = d.pose(self.data)
                self.red = (
                    self.capability == "red_light"
                    and elapsed >= 0.8
                    and (elapsed - 0.8) % 4.4 < 1.8
                )
                if self.red and not previous_red:
                    watch_start = elapsed
                    red_origin = None
                    reds += 1
                if self.red and elapsed - watch_start >= 0.4:
                    if red_origin is None:
                        red_origin = p[:2].copy()
                    if np.linalg.norm(p[:2] - red_origin) > 0.03:
                        return self.result(False, "红灯时移动超过三厘米，本轮被发现")
                if self.capability == "red_light":
                    self.model.geom_pos[self.model.geom("traffic_green").id, 2] = (
                        -0.4 if self.red else 0.45
                    )
                    self.model.geom_pos[self.model.geom("traffic_red").id, 2] = (
                        0.45 if self.red else -0.4
                    )
                previous_red = self.red
                if not self.red:
                    d.command[:3] = [
                        0.5 if self.capability != "red_light" else 0.7,
                        0,
                        np.clip(-yaw * 2 - p[1] * 3, -1, 1),
                    ]
                self.metrics.update(distance_m=float(p[0]), red_lights=reds)
                if p[0] >= self.length:
                    return self.result(True, "已越过终点线")
            self.tick()
            if self.capability == "tug":
                poses = [d.pose(self.data)[0] for d in self.drivers]
                marker = self.data.xpos[self.model.body("rope_8").id]
                gap = np.linalg.norm(
                    self.data.site_xpos[self.model.site("rope_end").id]
                    - self.data.site_xpos[self.model.site("rope_b").id]
                )
                self.metrics.update(rope_gap_m=float(gap), marker_x_m=float(marker[0]))
                if gap > 0.05:
                    return self.result(False, "绳端连接异常，已暂停本轮")
                losers = [i for i, p in enumerate(poses) if p[2] < -0.05]
                if losers:
                    return self.result(
                        True,
                        "本轮已分出胜负",
                        winner="b" if losers == [0] else "a" if losers == [1] else "draw",
                    )
            else:
                upright = float(self.data.xmat[self.drivers[0].body].reshape(3, 3)[2, 2])
                fallen = fallen + 1 if upright < 0.5 else 0
                if fallen >= 15:
                    return self.result(False, "身体失稳，已暂停物理")
            self.metrics["elapsed_seconds"] = float(self.data.time - start)
            deadline += 0.02
            await asyncio.sleep(max(0.001, deadline - time.monotonic()))
        if self.capability == "tug":
            x = self.metrics["marker_x_m"]
            return self.result(
                True, "回合结束，按绳中点判定", winner="a" if x < 0 else "b" if x > 0 else "draw"
            )
        return self.result(False, "时限内未越过终点线")

    def result(self, verified, message, **extra):
        return dict(verified=verified, message=message, **self.metrics, **extra)

    async def stop(self):
        for d in self.drivers:
            d.command[:] = 0

    async def reset(self):
        self.reset_state()

    def geometry(self):
        return dict(self.visual)

    async def snapshot(self):
        ducks = []
        for i, d in enumerate(self.drivers):
            p, yaw = d.pose(self.data)
            ducks.append(
                dict(
                    id="ab"[i],
                    position=p.tolist(),
                    yaw=yaw,
                    fallen=bool(self.data.xmat[d.body].reshape(3, 3)[2, 2] < 0.5),
                )
            )
        follow = ducks[0]["position"]
        camera = {}
        if self.capability == "tug":
            follow = np.mean([d["position"] for d in ducks], axis=0).tolist()
            camera["camera_radius_m"] = (
                float(np.linalg.norm(np.array(ducks[1]["position"]) - ducks[0]["position"])) * 0.5
                + 0.15
            )
        return dict(
            physics=True,
            runtime="mujoco_cpu_generic_policy_game",
            sim_time=float(self.data.time),
            view_scene="duo" if self.capability == "tug" else "terrain",
            ducks=ducks,
            camera_follow=follow,
            **camera,
            geoms=[
                dict(
                    id=i,
                    position=self.data.geom_xpos[i].tolist(),
                    rotation=self.data.geom_xmat[i].tolist(),
                )
                for i in self.geom_ids
            ],
            annotations=[
                dict(
                    id="light",
                    text="红灯：站定" if self.red else "绿灯：前进",
                    position=[self.data.qpos[0] + 0.3, 0, 0.35],
                )
            ]
            if self.capability == "red_light"
            else [],
        )

    async def close(self):
        await self.stop()
