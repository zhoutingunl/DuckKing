"""FootstepNet 8→3 planning and the 61→14 landing policy, in sole coordinates.

This CPU demonstration uses measured MuJoCo sole poses (not robot contact
odometry). Blue marks are targets; red marks are actual measured landings.
"""

import math
import sys

import mujoco
import numpy as np

from .feature_policies import PolicyWorld, module


class FootstepsWorld(PolicyWorld):
    def configure_spec(self, spec):
        for i in range(12):
            body = spec.worldbody.add_body(name=f"mark_{i}", pos=[-1, -1, -0.01], mocap=True)
            body.add_geom(
                name=f"mark_{i}",
                type=mujoco.mjtGeom.mjGEOM_BOX,
                size=[0.027, 0.0205, 0.0003],
                rgba=[0.15, 0.5, 0.85, 0.65] if i < 6 else [0.9, 0.24, 0.15, 0.55],
                group=2,
                contype=0,
                conaffinity=0,
            )
        return spec

    def __init__(self, assets):
        super().__init__(assets, "footsteps")
        runtime = self.root / "footstep-runtime"
        sys.path.insert(0, str(runtime / "src"))
        self.runtime = module(runtime / "scripts/infer_policy.py", "feature_footsteps_runtime")
        self.sites = [self.model.site(n + "_foot").id for n in ("left", "right")]

    def sole(self, index):
        site = self.sites[index]
        # Foot sites use the sole's forward axis in the upstream tracking task.
        rotation = self.data.site_xmat[site].reshape(3, 3)
        pos = self.data.site_xpos[site] + rotation[:, 0] * 0.007
        return np.array([pos[0], pos[1], math.atan2(rotation[1, 0], rotation[0, 0])])

    def mark(self, number, pose):
        index = self.model.body(f"mark_{number}").mocapid[0]
        self.data.mocap_pos[index] = [pose[0], pose[1], 0.001 if number < 6 else 0.002]
        self.data.mocap_quat[index] = [math.cos(pose[2] / 2), 0, 0, math.sin(pose[2] / 2)]

    async def perform(self, command):
        self.active_policy = self.policy
        self.metrics = {"steps_completed": 0, "landing_errors_mm": []}
        goal = self.sole(0) + [0.20, 0, 0]
        follower = self.runtime.FootstepFollower(
            self.model, str(self.root / "policies/footsteps/footstepnet.onnx"), goal, "left", None
        )
        count = 0
        for _ in range(600):
            self.command[:] = 0
            self.command[:3] = follower.update(self.data)
            if follower.target is not None:
                self.mark(min(count, 5), follower.target)
            if len(follower.errors) > count:
                error, yaw_error = follower.errors[-1]
                self.mark(min(count, 5) + 6, follower.landed[-1][0])
                self.metrics["landing_errors_mm"].append(round(error * 1000, 1))
                count = len(follower.errors)
                self.metrics["steps_completed"] = count
                if error > 0.025 or yaw_error > math.radians(10):
                    return {
                        "verified": False,
                        "message": "落足超出目标范围，已暂停；红色为实际足迹",
                        **self.metrics,
                    }
                if count >= 6:
                    self.command[:] = 0
                    self.active_policy = self.walk
                    await self.advance(1)
                    return {
                        "verified": self.upright() > 0.8,
                        "message": "六次落足已完成并恢复站稳",
                        **self.metrics,
                    }
            await self.advance(0.02)
        return {"verified": False, "message": "规定时间内未完成六次落足，已暂停", **self.metrics}
