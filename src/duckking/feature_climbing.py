"""CPU climbing experiments. Geometry and supervisory poses are privileged state.

A continuous attempt uses inference and MuJoCo throughout. No recorded root
trajectory is played. These are fresh CPU attempts, not the selected GPU video.
"""

import json
import math
from collections import deque

import mujoco
import numpy as np

from .feature_playground import PlaygroundWorld
from .feature_policies import session


class ClimbingWorld(PlaygroundWorld):
    def configure_experiment(self, spec):
        if self.capability == "climb":
            path = (
                self.root
                / "playground/experiments/desk-climb/source/src/mjlab_microduck/robot"
                / "floor_desk_assets/geometry.json"
            )
            for entry in json.loads(path.read_text()):
                name = "course_" + entry["name"]
                args = dict(
                    name=name,
                    pos=entry["pos"],
                    group=2,
                    friction=[1, 0.005, 0.0001],
                    priority=1,
                    condim=3,
                    solref=[0.01, 1],
                    solimp=[0.95, 0.99, 0.001, 0.5, 2],
                    rgba=[0.68, 0.51, 0.3, 1],
                )
                if entry["type"] == "mesh":
                    mesh = spec.add_mesh(name=name)
                    mesh.uservert = np.array(entry["vertices"]).ravel()
                    args.update(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=name)
                else:
                    args.update(
                        type={
                            "box": mujoco.mjtGeom.mjGEOM_BOX,
                            "cylinder": mujoco.mjtGeom.mjGEOM_CYLINDER,
                            "capsule": mujoco.mjtGeom.mjGEOM_CAPSULE,
                        }[entry["type"]],
                        size=entry["size"] + [0] * (3 - len(entry["size"])),
                    )
                if entry.get("quat"):
                    args["quat"] = entry["quat"]
                spec.worldbody.add_geom(**args)
        else:
            # Unmirrored positive-y exit, as defined by exit_stage.py. 3 m shelf.
            for side in [-1, 1]:
                for label, pos, size in [
                    ("lower", [side * 0.0925, 0, 1.5], [0.03, 0.15, 1.5]),
                    ("upper", [side * 0.0925, 0.225, 3.2], [0.03, 0.375, 0.2]),
                ]:
                    spec.worldbody.add_geom(
                        name=f"course_wall_{side}_{label}",
                        type=mujoco.mjtGeom.mjGEOM_BOX,
                        pos=pos,
                        size=size,
                        group=2,
                        rgba=[0.58, 0.53, 0.48, 1],
                        friction=[0.9, 0.005, 0.0001],
                        priority=1,
                        condim=3,
                        solref=[0.01, 1],
                        solimp=[0.95, 0.99, 0.001, 0.5, 2],
                    )
            spec.worldbody.add_geom(
                name="course_platform",
                type=mujoco.mjtGeom.mjGEOM_BOX,
                pos=[0, 0.575, 2.97],
                size=[0.25, 0.425, 0.03],
                group=2,
                rgba=[0.4, 0.57, 0.6, 1],
                friction=[1, 0.005, 0.0001],
                priority=1,
                solref=[0.01, 1],
                solimp=[0.95, 0.99, 0.001, 0.5, 2],
            )

    def __init__(self, assets, capability):
        super().__init__(assets, capability)
        self.climber = session(
            self.root
            / (
                "policies/climb/models/climber.onnx"
                if capability == "climb"
                else "policies/chimney/policy.onnx"
            )
        )
        self.recover = session(
            self.root
            / (
                "policies/climb/models/getup.onnx"
                if capability == "climb"
                else "policies/circus-base/alpha_stand.onnx"
            )
        )
        if capability == "chimney":
            self.enter = session(self.root / "policies/chimney/enter/policy.onnx")
            self.exit = session(self.root / "policies/chimney/exit/policy.onnx")
        self.home = self.pol.default_pose.copy()
        self.brace = self.home.copy()
        self.brace[[2, 3, 4, 11, 12, 13]] = [-1.57, 0, 0, 1.57, 0, 0]
        self.base_gain = self.bam.model.actuator.kp
        self.reset_state()

    def reset_state(self):
        super().reset_state()
        self.phase = 0
        self.filtered = np.zeros(14, np.float32)
        if self.capability == "climb":
            self.data.qpos[:3] = [-0.08, 0, 0.125]
        else:
            self.data.qpos[:3] = [0, -0.45, 0.125]
        if hasattr(self, "base_gain"):
            self.bam.model.actuator.kp = self.base_gain
            self.pol.default_pose[:] = self.home
            self.policy = self.climber if self.capability == "climb" else self.enter
        self.data.qpos[self.pol.joint_qpos_indices] = self.pol.default_pose
        self.targets = deque([self.pol.default_pose.copy() for _ in range(6)], maxlen=6)
        self.bam.reset(self.data.qpos)
        mujoco.mj_forward(self.model, self.data)

    def tick(self):
        if self.capability == "climb" and self.phase == 1:
            obs = self.observations()[None]
            action = self.recover.run(None, {self.recover.get_inputs()[0].name: obs})[0][0]
            if action.shape != (14,) or not np.isfinite(action).all():
                raise ValueError("策略输出无效，已暂停物理")
            self.pol.last_action[:] = action
            alpha = np.full(14, 0.7, np.float32)
            alpha[5:9] = 0.5
            self.filtered = alpha * action + (1 - alpha) * self.filtered
            target = self.pol.default_pose + self.filtered
            for _ in range(4):
                self.targets.append(target.copy())
                self.bam.q_target[:] = self.targets[0]
                self.bam.update()
                mujoco.mj_step(self.model, self.data)
            if not np.isfinite(self.data.qpos).all():
                raise ValueError("物理数值异常，已暂停，请重置")
        else:
            super().tick()
            self.filtered = self.pol.last_action.copy()

    async def perform(self, command):
        if self.data.time > 0.001:
            raise ValueError("本轮已结束，请先重置场景再试")
        stable = 0.0
        highest = float(self.data.qpos[2])
        if self.capability == "climb":
            self.policy = self.climber
        else:
            self.policy = self.enter
        for _ in range(60 * 50):
            p = self.data.qpos[:3]
            if self.capability == "climb":
                if self.phase == 0 and p[0] >= 0.45 and any(self.feet_on("course_desktop")):
                    self.phase = 1
                    self.bam.model.actuator.kp = self.base_gain * 0.8
                landed = all(self.feet_on("course_desktop"))
            else:
                q = self.data.qpos[3:7]
                yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
                self.command[:] = 0
                if self.phase == 0:
                    self.command[7:] = [
                        -math.cos(yaw) * p[0] - math.sin(yaw) * p[1],
                        math.sin(yaw) * p[0] - math.cos(yaw) * p[1],
                        math.sin(yaw),
                        math.cos(yaw),
                        -0.25,
                        0,
                    ]
                    if abs(p[0]) < 0.04 and abs(p[1]) < 0.06 and self.upright() > 0.9:
                        self.phase = 1
                        self.policy = self.climber
                        self.pol.default_pose[:] = self.brace
                        self.pol.last_action[:] = 0
                elif self.phase == 1:
                    self.command[7] = -0.25
                    if (
                        min(self.data.xpos[f, 2] for f in self.feet) > 3.05
                        and self.upright() > 0.85
                    ):
                        self.phase = 2
                        self.policy = self.exit
                elif self.phase == 2:
                    self.command[7:] = [0.8 - p[1], 3.12 - p[2], -p[0], 0, -0.25, 0]
                    if p[1] > 0.6 and any(self.feet_on("course_platform")):
                        self.phase = 3
                        self.policy = self.recover
                        self.pol.default_pose[:] = self.home
                        self.pol.last_action[:] = 0
                landed = all(self.feet_on("course_platform")) and p[1] > 0.6
            await self.advance(0.02, allow_head_support=True)
            highest = max(highest, float(self.data.qpos[2]))
            stable = (
                stable + 0.02
                if landed and self.upright() > 0.85 and np.linalg.norm(self.data.qvel[:3]) < 0.08
                else 0
            )
            self.metrics.update(climb_height_m=highest, stable_seconds=stable, phase=self.phase)
            if stable >= 2:
                return self.result(True, "已到达平台并持续站稳")
            if self.data.time > 2 and self.data.qpos[2] < 0.065:
                return self.result(False, "身体落地，本轮攀爬未完成")
        return self.result(False, "时限内未完成攀爬与平台站稳")

    async def stop(self):
        await super().stop()
        if hasattr(self, "base_gain"):
            self.bam.model.actuator.kp = self.base_gain

    async def snapshot(self):
        state = await super().snapshot()
        state["camera_follow"] = state["ducks"][0]["position"]
        return state
