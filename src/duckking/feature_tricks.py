"""Released langli11 policies, with explicit commanders and measured outcomes.

Slalom waypoints are known to the commander, never claimed to be visual input.
Single-blade score uses contact force, not an animated lifted-leg pose.
"""

import math
from types import SimpleNamespace

import mujoco
import numpy as np

from .feature_policies import PolicyWorld, module, session
from .model_assets import geometry


class TricksWorld(PolicyWorld):
    def __init__(self, assets, capability):
        roller = capability != "runup_roll"
        self.assets, self.capability = assets, capability
        self.root = assets / "features"
        self.ip = module(self.root / "upstream/scripts/infer_policy.py", "feature_tricks_infer")
        robot = self.root / "tricks-source/src/mjlab_microduck/robot/microduck"
        spec = self.configure_spec(
            mujoco.MjSpec.from_file(str(robot / ("scene_rollers.xml" if roller else "scene.xml")))
        )
        self.model = spec.compile()
        self.model.opt.timestep = 0.005
        from bam.model import load_model

        limit = load_model(motor_name="xl330", model="m6").kt.value * 1.75
        self.model.actuator_forcerange[:, 0] = -limit
        self.model.actuator_forcerange[:, 1] = limit
        self.model.actuator_forcelimited[:] = 1
        self.data = mujoco.MjData(self.model)
        self.cone_ids = (
            {self.model.geom(f"slalom_{k}").id: k for k in range(8)}
            if capability == "roller_slalom"
            else {}
        )
        self.hit_cones = set()
        self.pol = self.ip.PolicyInference(
            self.model,
            self.data,
            walking_onnx_path=str(assets / "policies/velstand.onnx"),
            new_cmd_obs=True,
            use_projected_gravity=True,
        )
        self.walk = session(assets / "policies/velstand.onnx")
        self.policy = session(
            self.root
            / "policies/tricks/policies"
            / {
                "runup_roll": "roulade_elan_v2_ckpt3750.onnx",
                "roller_slalom": "roller_slalom_v2_ckpt2000.onnx",
                "roller_glide": "roller_glide_short_v15_ckpt1750.onnx",
            }[capability]
        )
        self.reset_with_policy = roller
        self.spawn_height = 0.0135 if roller else 0
        self.trial_started = False
        self.body = self.model.body("trunk_base").id
        self.feet = [
            self.model.body(n).id
            for n in (("ankle_l_v1", "ankle_r_v1") if roller else ("ankle_left", "ankle_right"))
        ]
        self.geom_ids = [
            i
            for i in range(self.model.ngeom)
            if self.model.geom_group[i] == 2 or self.model.geom(i).name.startswith("slalom_")
        ]
        self.foot_geoms = [
            {i for i in range(self.model.ngeom) if self.model.geom_bodyid[i] == foot}
            for foot in self.feet
        ]
        self.command = np.zeros(13, dtype=np.float32)
        self.delay_action = np.zeros(14, dtype=np.float32)
        self.bam = SimpleNamespace(reset=lambda _: None)
        self.metrics = {}
        self.stand = session(self.root / "policies/circus-base/alpha_stand.onnx")
        if roller:
            for j in range(self.model.njnt):
                if self.model.joint(j).name.startswith("passive_"):
                    self.model.dof_frictionloss[self.model.jnt_dofadr[j]] = 0.003
            # Wheels are descendants of the ankles, rather than ankle geoms.
            self.foot_geoms = []
            for foot in self.feet:
                bodies = {foot}
                for b in range(foot + 1, self.model.nbody):
                    if int(self.model.body_parentid[b]) in bodies:
                        bodies.add(b)
                self.foot_geoms.append(
                    {
                        i
                        for i in range(self.model.ngeom)
                        if self.model.geom_bodyid[i] in bodies
                        and (self.model.geom_contype[i] or self.model.geom_conaffinity[i])
                    }
                )
        self.reset_state()
        self.visual = geometry(self.model, self.geom_ids)

    def tick(self):
        self.pol.command[:] = self.command
        network = self.active_policy
        obs = self.pol.get_observations()
        action = network.run(None, {network.get_inputs()[0].name: obs[None]})[0][0]
        if action.shape != (14,) or not np.isfinite(action).all():
            raise ValueError("策略输出无效，已暂停物理")
        self.pol.last_action[:] = action
        self.pol.set_position_targets(self.pol.default_pose + action)
        for _ in range(4):
            mujoco.mj_step(self.model, self.data)
            for c in self.data.contact:
                if c.dist <= 0.002:
                    for g in (c.geom1, c.geom2):
                        if g in self.cone_ids:
                            self.hit_cones.add(self.cone_ids[g])
        if not np.isfinite(self.data.qpos).all():
            raise ValueError("物理数值异常，已暂停，请重置")

    def configure_spec(self, spec):
        if self.capability == "roller_slalom":
            for k in range(8):
                # Small physical markers, unlike the upstream virtual scoring cones.
                spec.worldbody.add_geom(
                    name=f"slalom_{k}",
                    type=mujoco.mjtGeom.mjGEOM_CYLINDER,
                    pos=[(k + 1.5) * 0.7, 0, 0.035],
                    size=[0.03, 0.035, 0],
                    rgba=[0.98, 0.4, 0.1, 1],
                    group=2,
                )
        return spec

    def blade_loads(self):
        loads = [0.0, 0.0]
        force = np.zeros(6)
        floor = self.model.geom("floor").id
        for i, c in enumerate(self.data.contact):
            if floor not in (c.geom1, c.geom2):
                continue
            other = c.geom2 if c.geom1 == floor else c.geom1
            for k, ids in enumerate(self.foot_geoms):
                if other in ids:
                    mujoco.mj_contactForce(self.model, self.data, i, force)
                    loads[k] += abs(float(force[0]))
        return loads

    async def perform(self, command):
        if self.trial_started:
            raise ValueError("本轮已结束，请先重置场景再试")
        self.trial_started = True
        origin = self.data.qpos[:2].copy()
        start = self.data.time
        self.metrics = {}
        gates, hits = set(), self.hit_cones
        prev_x = 0.0
        streak = peak = 0.0
        side = None
        rotation = peak_rotation = 0.0
        seconds = 8 if self.capability != "roller_slalom" else 28
        try:
            for _ in range(seconds * 50):
                t = self.data.time - start
                x, y = self.data.qpos[:2] - origin
                self.command[:] = 0
                if self.capability == "runup_roll":
                    self.active_policy = (
                        self.walk if t < 2 else self.policy if t < 4 else self.stand
                    )
                    self.command[0] = 0.2 if t < 2 else 0
                else:
                    self.active_policy = self.policy
                    self.command[0] = 0.3
                    if self.capability == "roller_glide":
                        self.command[7] = float(2 <= t < 6)
                    else:
                        q = self.data.qpos[3:7]
                        yaw = math.atan2(
                            2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2)
                        )
                        desired = math.atan2(0.3 * math.sin(math.pi * (x + 0.35) / 0.7) - y, 0.35)
                        error = math.atan2(math.sin(desired - yaw), math.cos(desired - yaw))
                        self.command[2] = np.clip(error, -0.25, 0.25)
                await self.advance(0.02, allow_head_support=True)
                x, y = self.data.qpos[:2] - origin
                self.metrics["distance_m"] = float(np.linalg.norm(self.data.qpos[:2] - origin))
                if self.capability == "runup_roll":
                    if 2 <= t < 4:
                        rotation += float(self.pol.get_base_ang_vel()[1]) * 0.02
                        peak_rotation = max(peak_rotation, rotation)
                    self.metrics["rotation_deg"] = math.degrees(peak_rotation)
                elif self.capability == "roller_glide":
                    loads = self.blade_loads()
                    dominant = (
                        int(loads[1] > loads[0])
                        if sum(loads) > 0.5 and max(loads) >= 0.9 * sum(loads)
                        else None
                    )
                    # Single load-bearing blade while actually moving.
                    speed = np.linalg.norm(self.data.qvel[:2])
                    if dominant is not None and speed >= 0.05 and 2 <= t < 6:
                        streak = streak + 0.02 if dominant == side else 0.02
                    else:
                        streak = 0
                    side = dominant
                    peak = max(peak, streak)
                    self.metrics["single_blade_seconds"] = peak
                else:
                    for k in range(8):
                        cx = (k + 1.5) * 0.7
                        if (x - cx) ** 2 + y * y < 0.1**2:
                            hits.add(k)
                        if (
                            prev_x < cx <= x
                            and abs(y) < 0.35
                            and y * math.sin(math.pi * cx / 0.7) > 0
                        ):
                            gates.add(k)
                    prev_x = x
                    self.metrics.update(gates_passed=len(gates), cones_hit=len(hits))
                    if x > 7:
                        break
                if self.capability != "runup_roll" and self.upright() < 0.5:
                    return {"verified": False, "message": "身体失稳，已暂停物理", **self.metrics}
        finally:
            self.command[:] = 0
        passed = self.upright() > 0.85
        if self.capability == "runup_roll":
            passed = passed and peak_rotation >= math.radians(260) and self.data.qpos[2] >= 0.09
        elif self.capability == "roller_glide":
            passed = passed and peak >= 0.4 and x > 0.5
        else:
            passed = passed and len(gates) == 8 and not hits
        return {
            "verified": bool(passed),
            "message": "按本轮实际运动、接触和姿态验收",
            **self.metrics,
        }

    async def reset(self):
        self.trial_started = False
        self.hit_cones.clear()
        await super().reset()

    async def snapshot(self):
        state = await super().snapshot()
        state["camera_follow"] = state["ducks"][0]["position"]
        return state
