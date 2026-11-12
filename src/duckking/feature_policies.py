"""CPU replay of pinned community policies, with their own BAM physical models."""

import asyncio
import importlib.util
import math
import sys
import time

import mujoco
import numpy as np
import onnxruntime as ort

from .feature_bam import compile_bam
from .model_assets import geometry


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("策略运行资源缺失，请安装功能场景资源")
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def session(path):
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    result = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
    if result.get_inputs()[0].shape[-1] != 61 or result.get_outputs()[0].shape[-1] != 14:
        raise ValueError("策略接口不匹配，未执行动作")
    return result


class PolicyWorld:
    def __init__(self, assets, capability):
        self.assets, self.capability = assets, capability
        self.root = assets / "features"
        self.ip = module(
            self.root / "upstream/scripts/infer_policy.py",
            "feature_infer_policy",
        )
        robot = self.root / "upstream/src/mjlab_microduck/robot/microduck"
        scene = robot / (
            "scene_backlash.xml"
            if capability in {"hop", "footsteps", "giant_ball"} or capability.startswith("terrain_")
            else "scene_allcollisions.xml"
        )
        if capability == "footsteps" or capability.startswith("terrain_"):
            scene = robot / "scene_walk_backlash.xml"
        if capability == "step":
            scene = self.root / (
                "step/training/microduck_rl_snapshot/src/mjlab_microduck/"
                "robot/microduck/scene_household_threshold.xml"
            )
        bam = self.ip.load_bam_model(self.ip.BAM_KP_FW, 7.6, 1.75)
        spec = self.configure_spec(mujoco.MjSpec.from_file(str(scene)))
        self.model, self.data, self.bam, _ = compile_bam(spec, bam)
        self.pol = self.ip.PolicyInference(
            self.model,
            self.data,
            walking_onnx_path=str(assets / "policies/velstand.onnx"),
            bam_ctrl=self.bam,
            new_cmd_obs=True,
            use_projected_gravity=True,
        )
        self.backlash = []
        if capability in {"hop", "footsteps", "giant_ball"} or capability.startswith("terrain_"):
            for joint in self.bam.joint_indexes:
                name = self.model.joint(joint).name
                passive = self.model.joint(f"passive_{name}_backlash").id
                self.backlash.append(
                    (self.model.jnt_qposadr[passive], self.model.jnt_dofadr[passive])
                )
        self.walk = session(assets / "policies/velstand.onnx")
        file = self.root / "policies" / capability / "policy.onnx"
        if capability == "step":
            file = self.root / "step/policies/step_up_walk.onnx"
            self.recovery = session(self.root / "step/policies/step_up_stand_recovery.onnx")
        if capability == "footsteps":
            file = self.root / "policies/footsteps/footsteps.onnx"
        self.policy = (
            session(file)
            if capability in {"hop", "flamingo", "step", "footsteps", "swing", "giant_ball"}
            or capability.startswith("terrain_")
            else self.walk
        )
        self.body = self.model.body("trunk_base").id
        self.geom_ids = [
            i
            for i in range(self.model.ngeom)
            if self.model.geom_group[i] == 2
            or (
                self.model.geom_bodyid[i] == 0
                and self.model.geom_type[i] != mujoco.mjtGeom.mjGEOM_PLANE
            )
        ]
        self.feet = [self.model.body(name).id for name in ("ankle_left", "ankle_right")]
        self.foot_geoms = [
            {
                i
                for i in range(self.model.ngeom)
                if self.model.geom_bodyid[i] == foot
                and (self.model.geom_contype[i] or self.model.geom_conaffinity[i])
            }
            for foot in self.feet
        ]
        self.visual = geometry(self.model, self.geom_ids)
        self.metrics = {}
        self.active_policy = self.walk
        self.command = np.zeros(13, dtype=np.float32)
        self.delay_action = np.zeros(14, dtype=np.float32)
        self.reset_state()

    def configure_spec(self, spec):
        return spec

    def reset_state(self):
        mujoco.mj_resetData(self.model, self.data)
        root = self.pol._trunk_qpos_adr
        self.data.qpos[root : root + 7] = [
            0,
            0,
            0.125 + getattr(self, "spawn_height", 0),
            1,
            0,
            0,
            0,
        ]
        self.data.qpos[self.pol.joint_qpos_indices] = self.pol.default_pose
        self.bam.reset(self.data.qpos)
        self.pol.set_position_targets(self.pol.default_pose)
        self.pol.last_action[:] = 0
        self.command[:] = 0
        self.delay_action[:] = 0
        self.active_policy = (
            self.policy
            if self.capability == "flamingo" or getattr(self, "reset_with_policy", False)
            else self.walk
        )
        mujoco.mj_forward(self.model, self.data)
        for _ in range(60):
            self.tick()
        self.metrics = {}

    def tick(self):
        self.pol.command[:] = self.command
        obs = self.pol.get_observations()
        if self.backlash:
            obs[6:20] += self.data.qpos[[p for p, _ in self.backlash]]
            obs[20:34] += self.data.qvel[[v for _, v in self.backlash]]
        network = self.active_policy
        action = network.run(None, {network.get_inputs()[0].name: obs[None]})[0][0]
        if action.shape != (14,) or not np.isfinite(action).all():
            raise ValueError("策略输出无效，已暂停物理")
        self.pol.last_action[:] = action
        target = action
        if self.capability == "hop" and network is self.policy:
            target, self.delay_action = self.delay_action.copy(), action.copy()
        self.pol.set_position_targets(self.pol.default_pose + target)
        for _ in range(4):
            previous = self.data.time
            target_positions = self.bam.q_target.copy()
            if self.backlash:
                self.bam.q_target[:] -= self.data.qpos[[p for p, _ in self.backlash]]
            self.bam.update()
            self.bam.q_target[:] = target_positions
            mujoco.mj_step(self.model, self.data)
            if observer := getattr(self, "substep_observer", None):
                observer()
            if self.data.time <= previous or not np.isfinite(self.data.qpos).all():
                raise ValueError("物理数值异常，已暂停，请重置")

    def upright(self):
        return float(self.data.xmat[self.body].reshape(3, 3)[2, 2])

    def support(self):
        def environment(geom):
            body = int(self.model.geom_bodyid[geom])
            while body and body != self.body:
                body = int(self.model.body_parentid[body])
            return body != self.body

        return [
            any(
                (
                    (int(c.geom1) in ids and environment(c.geom2))
                    or (int(c.geom2) in ids and environment(c.geom1))
                )
                and c.dist < 0.002
                for c in self.data.contact
            )
            for ids in self.foot_geoms
        ]

    def clearance(self):
        # Collision proxies on the soles, never root-height change as "jump height".
        heights = []
        for ids in self.foot_geoms:
            bottoms = []
            for i in ids:
                rotation = self.data.geom_xmat[i].reshape(3, 3)
                kind = self.model.geom_type[i]
                size = self.model.geom_size[i]
                z = float(self.data.geom_xpos[i, 2])
                if kind == mujoco.mjtGeom.mjGEOM_MESH:
                    mesh = self.model.geom_dataid[i]
                    start = self.model.mesh_vertadr[mesh]
                    vertices = self.model.mesh_vert[start : start + self.model.mesh_vertnum[mesh]]
                    bottoms.append(z + float(np.einsum("ij,j->i", vertices, rotation[2]).min()))
                    continue
                if kind == mujoco.mjtGeom.mjGEOM_SPHERE:
                    extent = size[0]
                elif kind == mujoco.mjtGeom.mjGEOM_CAPSULE:
                    extent = size[0] + abs(rotation[2, 2]) * size[1]
                elif kind == mujoco.mjtGeom.mjGEOM_CYLINDER:
                    extent = size[0] * np.linalg.norm(rotation[2, :2]) + size[1] * abs(
                        rotation[2, 2]
                    )
                elif kind == mujoco.mjtGeom.mjGEOM_ELLIPSOID:
                    extent = np.linalg.norm(rotation[2] * size)
                else:
                    extent = float(np.abs(rotation[2]) @ size)
                bottoms.append(z - extent)
            heights.append(min(bottoms) if bottoms else 0)
        return heights

    async def advance(self, seconds, observer=None, *, allow_head_support=False):
        deadline = time.monotonic()
        for _ in range(round(seconds * 50)):
            self.tick()
            self.metrics.update(sim_time=float(self.data.time), support_feet=sum(self.support()))
            if not allow_head_support and self.upright() < 0.3:
                raise ValueError("身体失稳，已暂停；可重置后再试")
            if observer:
                observer()
            deadline += 0.02
            await asyncio.sleep(max(0.001, deadline - time.monotonic()))

    async def perform(self, command):
        if self.capability == "hop":
            if self.upright() < 0.8 or not all(self.support()):
                raise ValueError("请先重置，让双脚站稳后再起跳")
            self.active_policy = self.walk
            self.command[:] = 0
            await self.advance(1)
            self.active_policy = self.policy
            self.delay_action[:] = self.pol.last_action
            maximum = [0.0]

            def observe():
                maximum[0] = max(maximum[0], min(self.clearance()))
                self.metrics["max_clearance_m"] = maximum[0]

            await self.advance(3, observe)
            self.active_policy = self.walk
            await self.advance(1)
            passed = maximum[0] >= 0.015 and all(self.support()) and self.upright() > 0.8
            return {
                "verified": passed,
                "message": "已起跳、落地并站稳" if passed else "本轮未同时满足起跳与落地站稳条件",
                **self.metrics,
            }
        if self.capability == "flamingo":
            self.active_policy = self.policy
            side = 1 if command.action == "lift_left" else -1
            if command.action != "lower":
                self.command[:3] = [1, side, 0]
                peak = [0.0]
                index = 0 if side == 1 else 1

                def observe():
                    peak[0] = max(peak[0], self.clearance()[index])
                    self.metrics["max_clearance_m"] = peak[0]

                await self.advance(4, observe)
                lifted = peak[0] > 0.035
            else:
                lifted = True
            self.command[:] = 0
            await self.advance(3)
            passed = lifted and all(self.support()) and self.upright() > 0.8
            return {
                "verified": passed,
                "message": "已放下脚并站稳" if passed else "抬脚或恢复站稳未通过",
                **self.metrics,
            }
        if self.capability == "step":
            self.active_policy = self.policy
            self.command[:3] = [0.3, 0, 0]
            reached = False
            for _ in range(400):
                await self.advance(0.02, allow_head_support=True)
                reached = all(
                    self.data.xpos[i, 0] > 0.36 and self.data.xpos[i, 2] > 0.04 for i in self.feet
                )
                if reached:
                    break
            self.command[:] = 0
            self.active_policy = self.recovery
            await self.advance(8, allow_head_support=True)
            on_platform = all(
                self.data.xpos[i, 0] > 0.32 and abs(self.data.xpos[i, 1]) < 0.4 for i in self.feet
            )
            speed = float(np.linalg.norm(self.data.qvel[:2]))
            passed = reached and on_platform and self.upright() > 0.8 and speed < 0.05
            return {
                "verified": passed,
                "message": "双脚已上台并恢复站稳" if passed else "跨越或站稳条件未达标",
                "horizontal_speed_m_s": speed,
                "upright": self.upright(),
                **self.metrics,
            }
        raise ValueError("此策略的控制适配尚未完成")

    async def stop(self):
        self.command[:] = 0
        # A frozen experiment retains the actual pose; reset is explicit. Never
        # switch a falling or seated body blindly to a walking policy.

    async def reset(self):
        self.reset_state()

    def geometry(self):
        return dict(self.visual)

    async def snapshot(self):
        root = self.pol._trunk_qpos_adr
        q = self.data.qpos[root + 3 : root + 7]
        yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
        return {
            "physics": True,
            "runtime": "mujoco_cpu_bam_onnx",
            "sim_time": float(self.data.time),
            "view_scene": "ball",
            "ducks": [
                {
                    "id": "a",
                    "position": self.data.qpos[root : root + 3].tolist(),
                    "yaw": yaw,
                    "fallen": self.upright() < 0.3,
                }
            ],
            "geoms": [
                {
                    "id": i,
                    "position": self.data.geom_xpos[i].tolist(),
                    "rotation": self.data.geom_xmat[i].tolist(),
                }
                for i in self.geom_ids
            ],
        }

    async def close(self):
        await self.stop()
