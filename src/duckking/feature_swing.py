"""Self-pumped retained swing: released ONNX, elastic tendons and BAM actuators."""

import math
import os

import mujoco
import numpy as np

from .feature_bam import compile_bam
from .feature_policies import PolicyWorld, module, session
from .feature_source import scene_builder
from .model_assets import geometry


class SwingWorld(PolicyWorld):
    def __init__(self, assets):
        self.assets, self.capability = assets, "swing"
        root = assets / "features"
        source = root / "playground/src/mjlab_microduck/robot"
        self.ip = module(root / "upstream/scripts/infer_policy.py", "feature_infer_policy")
        constants = {
            "SWING_STRING_LENGTH": 0.38,
            "SWING_STRING_STIFFNESS": 2000,
            "SWING_STRING_LIMIT": 0.395,
            "SWING_HANG_LENGTH": 0.3822,
            "SWING_ANCHOR_HEIGHT": 0.75,
            "SWING_ATTACHMENT_Y": 0.088,
            "SWING_ATTACHMENT_Z": 0.085,
            "SWING_BOTTOM_TRUNK_Z": 0.2828,
        }
        spec = scene_builder(
            source / "microduck_constants.py",
            "get_swing_spec",
            {
                **constants,
                "mujoco": mujoco,
                "os": os,
                "MICRODUCK_ALLCOLLISIONS_XML": source / "microduck/robot_allcollisions.xml",
            },
        )
        spec.worldbody.add_geom(
            type=mujoco.mjtGeom.mjGEOM_PLANE,
            name="floor",
            size=[2, 2, 0.01],
            rgba=[0.9, 0.9, 0.85, 1],
        )
        motor = self.ip.load_bam_model(self.ip.BAM_KP_FW, 7.35, None)
        self.model, self.data, self.bam, _ = compile_bam(spec, motor)
        self.bam.vin_drop_gain = 0.1
        self.policy = session(root / "policies/swing/policy.onnx")
        self.pol = self.ip.PolicyInference(
            self.model,
            self.data,
            walking_onnx_path=str(root / "policies/swing/policy.onnx"),
            bam_ctrl=self.bam,
            action_scale=0.7,
            new_cmd_obs=True,
            use_projected_gravity=True,
        )
        self.body = self.model.body("trunk_base").id
        self.geom_ids = [i for i in range(self.model.ngeom) if self.model.geom_group[i] == 2]
        self.visual = geometry(self.model, self.geom_ids)
        # Strings are massless physical tendons. Render their measured endpoints
        # as capsules; these visual-only descriptors do not apply a force.
        self.string_ids = [self.model.ngeom, self.model.ngeom + 1]
        for i in self.string_ids:
            self.visual["geoms"].append(
                {
                    "id": i,
                    "type": 3,
                    "size": [0.002, 0.19, 0],
                    "rgba": [0.65, 0.57, 0.38, 1],
                    "mesh": -1,
                }
            )
        self.command = np.zeros(13)
        self.reset_state()

    def reset_state(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:7] = [0, 0, 0.2828, 1, 0, 0, 0]
        pose = np.array([0, 0, -0.4079, 1.35, 0, 0.3491, 0.3491, 0, 0, 0, 0, 0.4079, -1.35, 0])
        self.data.qpos[self.pol.joint_qpos_indices] = pose
        self.bam.reset(self.data.qpos)
        self.pol.last_action[:] = 0
        self.targets = [pose.copy() for _ in range(8)]
        self.metrics = {"swing_span_deg": 0, "phase": "ready"}
        mujoco.mj_forward(self.model, self.data)

    def tick(self):
        rotation = self.data.xmat[self.body].reshape(3, 3)
        self.pol.command[:] = 0
        self.pol.command[:3] = [0, rotation[0, 1], rotation[2, 1]]
        obs = self.pol.get_observations()
        action = self.policy.run(None, {self.policy.get_inputs()[0].name: obs[None]})[0][0]
        if not np.isfinite(action).all():
            raise ValueError("策略输出无效，已暂停")
        self.pol.last_action[:] = action
        target = self.pol.default_pose + 0.7 * action
        for _ in range(4):
            self.targets.append(target.copy())
            self.targets = self.targets[-8:]
            self.bam.q_target[:] = self.targets[-6]  # nominal 25 ms servo delay
            self.bam.update()
            mujoco.mj_step(self.model, self.data)
        if not np.isfinite(self.data.qpos).all():
            raise ValueError("物理数值异常，已暂停；请重新准备场景。")

    def endpoints(self):
        return [
            (
                self.data.site_xpos[self.model.site("swing_anchor_" + side).id],
                self.data.site_xpos[self.model.site("swing_attach_" + side).id],
            )
            for side in ("left", "right")
        ]

    async def perform(self, command):
        low, high, valid = 0.0, 0.0, True
        minimum, maximum, lateral_max = 1.0, 0.0, 0.0

        def measure():
            nonlocal low, high, valid, minimum, maximum, lateral_max
            ends = self.endpoints()
            vector = np.mean([b - a for a, b in ends], axis=0)
            angle = math.degrees(math.atan2(vector[0], -vector[2]))
            low, high = min(low, angle), max(high, angle)
            lengths = [float(np.linalg.norm(b - a)) for a, b in ends]
            lateral = abs(float(vector[1]))
            minimum, maximum = min(minimum, *lengths), max(maximum, *lengths)
            lateral_max = max(lateral_max, lateral)
            valid &= min(lengths) >= 0.370 and max(lengths) <= 0.394 and lateral <= 0.02
            self.metrics.update(
                swing_span_deg=high - low,
                string_lengths_m=lengths,
                lateral_m=lateral,
                geometry_valid=bool(valid),
                minimum_string_m=minimum,
                maximum_string_m=maximum,
                maximum_lateral_m=lateral_max,
            )

        await self.advance(24, measure, allow_head_support=True)
        passed = valid and high - low >= 20
        return {
            "verified": passed,
            "message": "已通过本轮摆幅与绳长检查" if passed else "本轮摆幅或悬挂几何未达标，已暂停",
            **self.metrics,
        }

    def support(self):
        return []  # retained seat, not standing on two feet

    async def snapshot(self):
        state = await super().snapshot()
        for id_, (a, b) in zip(self.string_ids, self.endpoints(), strict=True):
            z = (b - a) / np.linalg.norm(b - a)
            x = np.cross([0, 1, 0], z)
            x /= np.linalg.norm(x)
            y = np.cross(z, x)
            state["geoms"].append(
                {
                    "id": id_,
                    "position": ((a + b) / 2).tolist(),
                    "rotation": np.column_stack([x, y, z]).flatten().tolist(),
                }
            )
        state["view_scene"] = "swing"
        state["ducks"][0]["fallen"] = False  # orientation is expected to swing through large arcs
        return state
