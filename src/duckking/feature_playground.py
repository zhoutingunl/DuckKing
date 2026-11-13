"""CPU adapters for Vottivott's released running, blind ball and platform policies.

The policies control joint targets only. Free bases, ball motion, takeoff and
landings are computed by MuJoCo. Nominal BAM voltage/delay are fixed, not a
reproduction of the upstream randomized batch evaluation or hardware evidence.
"""

import json
import math
from collections import deque

import mujoco
import numpy as np

from .feature_bam import compile_bam
from .feature_policies import PolicyWorld, module, session
from .feature_source import source_symbols
from .model_assets import geometry


class PlaygroundWorld(PolicyWorld):
    def __init__(self, assets, capability, *, variant=None):
        self.assets, self.capability = assets, capability
        self.height = variant or 10
        self.root = assets / "features"
        source = self.root / "playground/src/mjlab_microduck/robot"
        self.ip = module(self.root / "upstream/scripts/infer_policy.py", "feature_infer_policy")
        robot = source / "microduck"
        spec = mujoco.MjSpec.from_file(
            str(
                robot
                / (
                    "robot_walk.xml"
                    if capability in {"running", "stilts"}
                    else "robot_allcollisions.xml"
                )
            )
        )
        if capability == "stilts":
            from .feature_playground_more import stilt_spec

            spec = stilt_spec(spec, source, self.height)
        if capability in {"long_jump", "backflip", "climb", "chimney"}:
            helpers = source_symbols(
                source / "long_jump_robot.py",
                {
                    "SKIP_MESH_PREFIXES",
                    "SKIP_BODIES",
                    "EXPLICIT_PAIR_BODIES",
                    "EXCLUDED_BODY_PAIRS",
                    "_is_collision_geom",
                    "add_full_collision_geoms",
                    "add_leg_fold_pairs",
                },
                {"mujoco": mujoco},
            )
            helpers["add_full_collision_geoms"](spec)
            helpers["add_leg_fold_pairs"](spec)
        if capability == "long_jump":
            for name, center, color in (
                ("platform_a", [-0.3, 0, -0.05], [0.62, 0.52, 0.40, 1]),
                ("platform_b", [0.6, 0, -0.3], [0.45, 0.55, 0.62, 1]),
            ):
                spec.worldbody.add_geom(
                    name=name,
                    type=mujoco.mjtGeom.mjGEOM_BOX,
                    size=[0.3, 0.3, 0.4],
                    pos=center,
                    rgba=color,
                    friction=[1, 0.005, 0.0001],
                    condim=3,
                    priority=1,
                    solref=[0.01, 1],
                    solimp=[0.95, 0.99, 0.001, 0.5, 2],
                )
        if capability == "backflip":
            from .feature_playground_more import flip_stage

            flip_stage(spec)
        if capability == "basketball":
            ball = spec.worldbody.add_body(name="ball", pos=[0, 0, 0.12])
            ball.add_freejoint(name="ball_root")
            ball.add_geom(
                name="ball_sphere",
                type=mujoco.mjtGeom.mjGEOM_SPHERE,
                size=[0.12, 0, 0],
                mass=0.62,
                rgba=[0.91, 0.42, 0.12, 1],
                friction=[1.2, 0.01, 0.001],
                priority=1,
                condim=4,
                group=2,
            )
            # Thin, massless visual seams expose ball rotation. The sole
            # collision remains the released 120 mm sphere, not these segments.
            for plane in range(3):
                for segment in range(32):
                    points = []
                    for angle in (segment * math.tau / 32, (segment + 1) * math.tau / 32):
                        p = [0, 0, 0]
                        p[(plane + 1) % 3] = 0.1205 * math.cos(angle)
                        p[(plane + 2) % 3] = 0.1205 * math.sin(angle)
                        points.extend(p)
                    ball.add_geom(
                        type=mujoco.mjtGeom.mjGEOM_CAPSULE,
                        size=[0.0012, 0, 0],
                        fromto=points,
                        mass=0,
                        contype=0,
                        conaffinity=0,
                        rgba=[0.14, 0.10, 0.08, 1],
                        group=2,
                    )
        if capability in {"climb", "chimney"}:
            self.configure_experiment(spec)
        spec.worldbody.add_geom(
            name="floor",
            type=mujoco.mjtGeom.mjGEOM_PLANE,
            size=[0, 0, 0.01],
            friction=[1, 0.005, 0.0001],
        )
        motor = self.ip.load_bam_model(self.ip.BAM_KP_FW, 7.35, None)
        self.model, self.data, self.bam, _ = compile_bam(spec, motor)
        self.bam.vin_drop_gain = 0.1
        policy_path = self.root / "policies" / capability / "policy.onnx"
        if capability == "stilts":
            policy_path = self.root / "policies/stilts" / f"{self.height}cm/policy.onnx"
        if capability == "standup":
            policy_path = self.root / "policies/circus-base/alpha_stand.onnx"
        if capability == "climb":
            policy_path = self.root / "policies/climb/models/climber.onnx"
        if capability == "chimney":
            policy_path = self.root / "policies/chimney/enter/policy.onnx"
        self.policy = session(policy_path)
        self.pol = self.ip.PolicyInference(
            self.model,
            self.data,
            walking_onnx_path=str(assets / "policies/velstand.onnx"),
            bam_ctrl=self.bam,
            new_cmd_obs=True,
            use_projected_gravity=True,
        )
        self.bounds = None
        if capability in {"long_jump", "backflip"}:
            config = json.loads(policy_path.with_name("config.json").read_text())
            names = [self.model.joint(i).name for i in self.bam.joint_indexes]
            if config["joint_names"] != names or config["action_scale"] != 1:
                raise ValueError("策略关节顺序不匹配，未执行动作")
            self.pol.default_pose = np.array(config["joint_offset_rad"], dtype=np.float32)
            self.bounds = (
                np.array(config["action_bounds_lo"]),
                np.array(config["action_bounds_hi"]),
            )
        if capability == "basketball":
            signature = {i.name: i.shape for i in self.policy.get_inputs()}
            if signature != {"obs": [1, 61], "h_in": [1, 1, 256], "c_in": [1, 1, 256]}:
                raise ValueError("篮球记忆策略接口不匹配，未执行动作")
        self.body = self.model.body("trunk_base").id
        self.feet = [self.model.body(n).id for n in ("ankle_left", "ankle_right")]
        self.foot_geoms = [
            set(
                np.flatnonzero(
                    (self.model.geom_bodyid == body)
                    & ((self.model.geom_contype != 0) | (self.model.geom_conaffinity != 0))
                )
            )
            for body in self.feet
        ]
        if capability == "stilts":
            self.foot_geoms = [
                {self.model.geom(f"{side}_foot_collision").id} for side in ("left", "right")
            ]
        self.head_geoms = set(
            np.flatnonzero(self.model.geom_bodyid == self.model.body("jaw_soft").id)
        )
        self.floor = self.model.geom("floor").id
        self.geom_ids = [
            i
            for i in range(self.model.ngeom)
            if self.model.geom_group[i] == 2
            or self.model.geom(i).name in {"platform_a", "platform_b", "platform", "mat"}
            or self.model.geom(i).name.startswith("course_")
        ]
        self.visual = geometry(self.model, self.geom_ids)
        self.command = np.zeros(13, dtype=np.float32)
        self.reset_state()

    def reset_state(self):
        mujoco.mj_resetData(self.model, self.data)
        root = self.pol._trunk_qpos_adr
        x, z = (
            (-0.085, 0.468)
            if self.capability == "long_jump"
            else (0, 0.365 if self.capability == "basketball" else 0.125)
        )
        if self.capability == "stilts":
            z += self.height * 0.01
        elif self.capability == "backflip":
            x, z = -0.075, 1.36142
        elif self.capability == "standup":
            z = 0.055
        self.data.qpos[root : root + 7] = [x, 0, z, 1, 0, 0, 0]
        if self.capability == "backflip":
            self.data.qpos[root + 3 : root + 7] = [0, 0, 0, 1]
        elif self.capability == "standup":
            self.data.qpos[root + 3 : root + 7] = [0, 0, 1, 0]
        self.data.qpos[self.pol.joint_qpos_indices] = self.pol.default_pose
        self.bam.reset(self.data.qpos)
        self.pol.last_action[:] = 0
        self.command[:] = 0
        if self.capability == "long_jump":
            self.command[7:9] = [1, 0.25 / 0.3]
        self.memory = {name: np.zeros((1, 1, 256), np.float32) for name in ("h_in", "c_in")}
        self.previous_velocity = np.zeros(14, dtype=np.float32)
        self.targets = deque([self.pol.default_pose.copy() for _ in range(6)], maxlen=6)
        self.invalid_contact = False
        self.metrics = {}
        mujoco.mj_forward(self.model, self.data)

    def observations(self):
        self.pol.command[:] = self.command
        obs = self.pol.get_observations().astype(np.float32)
        velocity = obs[20:34].copy()
        obs[20:34] = self.previous_velocity
        self.previous_velocity = velocity
        if self.capability == "basketball":
            obs[51:61] = 0  # No ball position, velocity, contact or camera input.
        return obs

    def tick(self):
        inputs = {self.policy.get_inputs()[0].name: self.observations()[None]}
        if self.capability == "basketball":
            inputs.update(self.memory)
        outputs = self.policy.run(None, inputs)
        action = outputs[0][0]
        if action.shape != (14,) or any(not np.isfinite(v).all() for v in outputs):
            raise ValueError("策略输出无效，已暂停物理")
        if self.bounds and (
            np.any(action < self.bounds[0] - 1e-5) or np.any(action > self.bounds[1] + 1e-5)
        ):
            raise ValueError("策略输出超出关节限位，已暂停物理")
        if self.capability == "basketball":
            self.memory = {"h_in": outputs[1], "c_in": outputs[2]}
        self.pol.last_action[:] = action
        target = self.pol.default_pose + action
        for _ in range(4):
            self.targets.append(target.copy())
            self.bam.q_target[:] = self.targets[0]  # Nominal 25 ms motor delay.
            self.bam.update()
            previous = self.data.time
            mujoco.mj_step(self.model, self.data)
            if self.data.time <= previous or not np.isfinite(self.data.qpos).all():
                raise ValueError("物理数值异常，已暂停；请重新准备场景。")
            for contact in self.data.contact:
                if contact.dist > 0.001:
                    continue
                a, b = int(contact.geom1), int(contact.geom2)
                if self.floor in {a, b} and (
                    a in set.union(*self.foot_geoms) or b in set.union(*self.foot_geoms)
                ):
                    self.invalid_contact = True
                if self.capability == "long_jump" and (
                    a in self.head_geoms or b in self.head_geoms
                ):
                    if a in self.environment_geoms() or b in self.environment_geoms():
                        self.invalid_contact = True

    def environment_geoms(self):
        return {self.floor, self.model.geom("platform_a").id, self.model.geom("platform_b").id}

    def feet_on(self, name):
        geom = self.model.geom(name).id
        return [
            any(
                c.dist < 0.002
                and ((c.geom1 in ids and c.geom2 == geom) or (c.geom2 in ids and c.geom1 == geom))
                for c in self.data.contact
            )
            for ids in self.foot_geoms
        ]

    def start_condition(self, action):
        if self.capability != "basketball":
            return None
        if self.data.time <= 0.001:
            return {"mode": "continue", "reason": ""}
        ball = self.model.body("ball").id
        offset = float(np.linalg.norm(self.data.xpos[self.body, :2] - self.data.xpos[ball, :2]))
        supported = any(self.feet_on("ball_sphere"))
        if (self.invalid_contact or not supported or offset > 0.16
                or self.upright() < math.cos(math.radians(55))
                or self.data.xpos[self.body, 2] < 0.17):
            return {"mode": "restart", "reason": "小鸭已离开篮球，正在自动恢复起点。"}
        return {"mode": "continue", "reason": ""}

    async def perform(self, command):
        # Preserve the pose, velocity and recurrent memory for supported ball
        # commands. Finite courses still require a fresh trial at the worker boundary.
        if self.capability != "basketball" and self.data.time > 0.001:
            raise ValueError("本轮已结束；再次点击动作会自动重置起点。")
        if self.capability == "stilts":
            return await self.stilt_trial()
        if self.capability == "standup":
            return await self.recovery_trial(command.action)
        if self.capability == "backflip":
            return await self.flip_trial()
        if self.capability == "running":
            return await self.run_trial()
        if self.capability == "basketball":
            return await self.ball_trial(command.action)
        return await self.jump_trial()

    async def recovery_trial(self, action):
        if action == "recover_front":
            self.data.qpos[:7] = [0, 0, 0.075, 0.70710678, 0, 0.70710678, 0]
            mujoco.mj_forward(self.model, self.data)
        stable = 0
        for _ in range(600):
            await self.advance(0.02, allow_head_support=True)
            stable = stable + 1 if self.upright() > 0.85 and all(self.support()) else 0
            self.metrics.update(stable_seconds=stable * 0.02, upright=self.upright())
            if stable >= 50:
                return self.result(True, "已从卧姿恢复并双脚站稳一秒")
        return self.result(False, "本轮未能从卧姿恢复站稳")

    async def stilt_trial(self):
        self.command[0] = 0.15
        start = self.data.qpos[:2].copy()
        for _ in range(500):
            await self.advance(0.02, allow_head_support=True)
            self.metrics.update(
                height_cm=self.height,
                distance_m=float(np.linalg.norm(self.data.qpos[:2] - start)),
                upright=self.upright(),
            )
            if self.upright() < 0.65:
                return self.result(False, "高跷失稳，已暂停")
        return self.result(self.metrics["distance_m"] > 0.3, "高跷试跑结束，按实际位移和姿态验收")

    async def flip_trial(self):
        self.command[:] = 0
        self.command[7:9] = [0.5, -1]
        rotation, peak, stable, airborne, previous = 0.0, 0.0, 0, False, 0.0
        for _ in range(600):
            await self.advance(0.02, allow_head_support=True)
            # Unwrap the body-forward vector in its actual launch sagittal plane.
            forward = self.data.xmat[self.body].reshape(3, 3)[:, 0]
            pitch = math.atan2(float(forward[2]), -float(forward[0]))
            rotation += math.atan2(math.sin(pitch - previous), math.cos(pitch - previous))
            previous = pitch
            peak = max(peak, abs(rotation))
            on_mat = self.feet_on("mat")
            airborne |= self.data.time > 0.1 and not any(self.support())
            stable = stable + 1 if all(on_mat) and self.upright() > 0.85 else 0
            self.metrics.update(
                rotation_deg=math.degrees(peak),
                stable_seconds=stable * 0.02,
                target_support_feet=sum(on_mat),
                drop_m=0.8,
            )
            if self.invalid_contact:
                return self.result(False, "已离开软垫并触地，未通过完整落地验收")
        return self.result(
            airborne and peak > 5.2 and stable >= 50, "按完整转动、双脚落垫和持续站稳验收本轮"
        )

    async def run_trial(self):
        self.command[0] = 2.2
        speeds, start = [], self.data.qpos[:2].copy()
        for _ in range(250):
            await self.advance(0.02, allow_head_support=True)
            speed = float(self.data.xmat[self.body].reshape(3, 3)[:, 0] @ self.data.qvel[:3])
            speeds.append(speed)
            self.metrics.update(
                actual_speed_m_s=speed,
                mean_speed_m_s=float(np.mean(speeds)),
                distance_m=float(np.linalg.norm(self.data.qpos[:2] - start)),
                lateral_drift_m=abs(float(self.data.qpos[1] - start[1])),
            )
            if self.upright() < math.cos(math.radians(70)):
                return self.result(False, "快跑失稳，已暂停")
        return self.result(float(np.mean(speeds[50:])) >= 1, "快跑结束，速度与偏移按实际运动计算")

    async def ball_trial(self, action):
        self.command[0] = 0.10 if action == "roll_forward" else 0
        ball = self.model.body("ball").id
        ball_start = self.data.xpos[ball, :2].copy()
        supported = 0
        for _ in range(500):
            await self.advance(0.02, allow_head_support=True)
            contact = sum(self.feet_on("ball_sphere"))
            supported += int(contact > 0)
            offset = float(np.linalg.norm(self.data.xpos[self.body, :2] - self.data.xpos[ball, :2]))
            self.metrics.update(
                ball_offset_m=offset,
                support_feet=contact,
                ball_travel_m=float(np.linalg.norm(self.data.xpos[ball, :2] - ball_start)),
                supported_seconds=supported * 0.02,
            )
            if (
                self.invalid_contact
                or offset > 0.16
                or self.upright() < math.cos(math.radians(55))
                or self.data.xpos[self.body, 2] < 0.17
            ):
                return self.result(False, "已离开篮球或失稳，已暂停")
        return self.result(contact > 0 and supported >= 450, "篮球试跑结束，按实际支撑与姿态验收")

    async def jump_trial(self):
        # The worker cancels the previous task (and clears commands) before
        # every start. Restore the policy's scene command at this boundary.
        self.command[:] = 0
        self.command[7:9] = [1, 0.25 / 0.3]
        launched, landed, stable, supported_a, air, longest_air = False, False, 0, False, 0, 0
        takeoff_velocity = 0.0
        for _ in range(600):
            await self.advance(0.02, allow_head_support=True)
            on_a, on_b = self.feet_on("platform_a"), self.feet_on("platform_b")
            supported_a |= all(on_a)
            airborne = not any(on_a) and not any(on_b)
            if supported_a and airborne and not air:
                takeoff_velocity = float(self.data.qvel[2])
            air = air + 1 if airborne else 0
            if takeoff_velocity > 0.1:
                longest_air = max(longest_air, air)
            launched |= longest_air >= 5
            landed |= launched and all(on_b)
            speed = float(np.linalg.norm(self.data.qvel[:3]))
            stable = (
                stable + 1 if landed and all(on_b) and self.upright() > 0.85 and speed < 0.15 else 0
            )
            self.metrics.update(
                target_support_feet=sum(on_b),
                stable_seconds=stable * 0.02,
                distance_m=float(self.data.qpos[0] + 0.085),
                flight_seconds=longest_air * 0.02,
                gap_m=0.3,
                drop_m=0.25,
                launched=bool(launched),
                landed=bool(landed),
            )
            if self.invalid_contact or self.upright() < math.cos(math.radians(70)):
                return self.result(False, "落入间隙、头部触地或身体失稳，已暂停")
            if stable >= 50:
                return self.result(True, "已跨越间隙，双脚落台并稳定一秒")
        return self.result(False, "本轮未满足双脚落台并稳定一秒")

    def result(self, verified, message):
        return {"verified": bool(verified), "message": message, **self.metrics}

    async def snapshot(self):
        state = await super().snapshot()
        state["view_scene"] = self.capability
        if self.capability in {"running", "stilts"}:
            state["camera_follow"] = state["ducks"][0]["position"]
        if self.capability == "stilts":
            state["stilt_height_m"] = self.height * 0.01
        return state
