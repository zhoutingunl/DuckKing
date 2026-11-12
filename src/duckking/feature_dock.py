"""MicroDock v2 CPU adapter. Controller phases follow Vottivott's Apache source.

The tag estimate is simulation truth. USB contact is a geometric proxy, not an
electrical simulation. No body teleport is used after an explicit reset.
"""

import asyncio
import math
import os
import shutil
import sys
import tempfile

import mujoco
import numpy as np

from .feature_bam import SpecCompatibility, compile_bam
from .feature_policies import PolicyWorld, module, session
from .model_assets import geometry


class DockWorld(PolicyWorld):
    def __init__(self, assets, capability="dock"):
        self.assets, self.capability = assets, capability
        root = assets / "features"
        os.environ["MICRODUCK_RL_DIR"] = str(root / "upstream")
        os.environ["MICRODUCK_POLICY_DIR"] = str(assets / "policies")
        folder = root / "playground/hardware/microdock-v2/sim"
        sys.path.insert(0, str(folder))
        self.ds = module(folder / "docking_seated.py", "docking_seated")
        self.latency = module(folder / "latency.py", "dock_latency")
        self.dg, self.dk = self.ds.dg, self.ds.dk
        self.ip = self.dg._infer_policy()
        self.params = self.dk.Params() if capability == "dock_standing" else self.ds.seated.Params()
        self.dk.MAG_F = 4.0
        self.temporary = tempfile.TemporaryDirectory(prefix="duckking-dock-")
        robot = root / "upstream/src/mjlab_microduck/robot/microduck"
        # Upstream writes a generated scene alongside the robot XML. Give each
        # worker its own XML directory; share only immutable mesh assets.
        from pathlib import Path

        private = Path(self.temporary.name)
        for file in robot.iterdir():
            if file.is_file():
                shutil.copy2(file, private / file.name)
            elif file.is_dir():
                (private / file.name).symlink_to(file, target_is_directory=True)
        spec = self.dk.modify_robot(
            SpecCompatibility(self.dk.build_scene(self.params, str(private))), self.params
        )
        motor = self.ip.load_bam_model(self.ip.BAM_KP_FW, 7.6, 1.75)
        self.model, self.data, self.bam, _ = compile_bam(spec, motor)
        if capability == "dock":
            self.ds.seat_friction(self.model)
        self.pol = self.ip.PolicyInference(
            self.model,
            self.data,
            walking_onnx_path=str(assets / "policies/velstand.onnx"),
            sitstand_onnx_path=str(assets / "policies/alpha_sitstand.onnx"),
            bam_ctrl=self.bam,
            new_cmd_obs=True,
            use_projected_gravity=True,
        )
        self.pol.dock_session = session(folder.parent / "policy/scoot_dock.onnx")
        self.pol.undock_session = session(folder.parent / "policy/scoot_undock.onnx")
        if capability == "dock":
            self.latency.enable(self.pol, self.bam, seed=41, official=False, scoot=True)
        self.body = self.model.body("trunk_base").id
        self.geom_ids = [
            i
            for i in range(self.model.ngeom)
            if self.model.geom_type[i] != mujoco.mjtGeom.mjGEOM_PLANE
            and (
                self.model.geom_group[i] == 2
                or self.model.body(self.model.geom_bodyid[i]).name in {"world", "hood"}
            )
        ]
        self.visual = geometry(self.model, self.geom_ids)
        self.command = np.zeros(13)
        self.metrics = {}
        self.reset_state()

    def reset_state(self):
        self.dg.reset(
            self.model,
            self.data,
            self.bam,
            self.pol,
            x=0.45,
            y=0.015,
            yaw=math.radians(178),
            z=0.125,
        )
        self.pol.sit_mode = False
        self.pol.current_policy = "walking"
        self.pol.ort_session = self.pol.walking_session
        self.virtual_battery_percent = 20.0
        self.metrics = {
            "virtual_battery_percent": 20,
            "charging_proxy": False,
            "phase": "ready",
            "magnet_n": 4.0,
        }

    async def ticks(self, count, phase, velocity=(0, 0, 0), until=None):
        for _ in range(count):
            vx, vy, wz = velocity() if callable(velocity) else velocity
            self.pol.set_vel_cmd(vx, vy, wz)
            self.dg.step_control(
                self.model,
                self.data,
                self.bam,
                self.pol,
                frame_cb=lambda _: self.dk.magnet(self.model, self.data),
            )
            error = self.dk.tip_error(self.model, self.data)
            connected = bool(self.dk.connected(error))
            self.metrics.update(
                phase=phase,
                sim_time=float(self.data.time),
                charging_proxy=connected,
                tip_error_mm=error.tolist(),
            )
            if phase == "charging" and connected:
                self.virtual_battery_percent = min(100, self.virtual_battery_percent + 0.02)
            self.metrics["virtual_battery_percent"] = self.virtual_battery_percent
            if not np.isfinite(self.data.qpos).all():
                raise ValueError("物理数值异常，请重置")
            if until and until():
                return True
            await asyncio.sleep(0.02)
        return False

    def heading(self, target=0, gain=0.03, limit=0.3):
        return float(
            np.clip(gain * self.dg.wrap(target - self.dg.yaw_deg(self.data)), -limit, limit)
        )

    async def perform(self, command):
        if self.capability == "dock_standing":
            return await self.standing_trial(command)
        # Per-command telemetry is cleared by Worker; simulated charge belongs
        # to the world and must survive subsequent dock/undock commands.
        self.metrics["virtual_battery_percent"] = self.virtual_battery_percent
        if command.action == "undock":
            if not self.dk.connected(self.dk.tip_error(self.model, self.data)):
                raise ValueError("当前没有对接，请先完成回窝")
            start = float(self.data.qpos[0])
            self.pol.sit_mode = False
            self.pol.current_policy = "walking"
            self.pol.ort_session = self.pol.undock_session
            released = await self.ticks(
                500,
                "undock",
                lambda: (0.05, 0, self.heading()),
                lambda: self.data.qpos[0] >= start + 0.07,
            )
            await self.ticks(25, "halt")
            self.pol.current_policy = "sit"
            self.pol.ort_session = self.pol.sit_session
            await self.ticks(175, "stand")
            self.pol.current_policy = "walking"
            self.pol.ort_session = self.pol.walking_session
            await self.ticks(150, "walk", (0.3, 0, 0))
            passed = released and self.upright() > 0.8 and self.data.qpos[2] > 0.1
            return {
                "verified": bool(passed),
                "message": "已离窝并站稳" if passed else "离窝或站稳条件未达标",
                **self.metrics,
            }
        if self.data.qpos[2] < 0.09 or self.dk.connected(self.dk.tip_error(self.model, self.data)):
            raise ValueError("当前已经坐下或对接；可离窝，或显式重置后再回窝")
        await self.ticks(40, "look")

        def approach():
            target = math.degrees(math.atan2(-(self.data.qpos[1] * 1000 + 29), -150))
            return 0.3, 0, self.heading(target, 0.035, 0.5)

        reached = await self.ticks(1500, "approach", approach, lambda: self.data.qpos[0] <= 0.2)
        if not reached:
            raise ValueError("未能走到转身位置，已暂停")
        await self.ticks(20, "halt")
        await self.ticks(
            600,
            "turn",
            lambda: (0, 0, np.sign(self.heading(6.6))),
            lambda: abs(self.dg.wrap(6.6 - self.dg.yaw_deg(self.data))) < 10,
        )
        await self.ticks(
            250,
            "align",
            lambda: (
                0,
                0,
                np.sign(self.heading(6.6))
                * (0.6 if abs(self.dg.wrap(6.6 - self.dg.yaw_deg(self.data))) > 4 else 0.45),
            ),
            lambda: abs(self.dg.wrap(6.6 - self.dg.yaw_deg(self.data))) < 1,
        )
        await self.ticks(25, "settle")
        self.pol.toggle_sit()
        still = 0
        for k in range(200):
            await self.ticks(1, "sit")
            moving = (
                np.linalg.norm(self.data.qvel[:3]) > 0.005
                or np.max(np.abs(self.data.qvel[self.bam.dof_indexes])) > 0.1
            )
            still = 0 if moving else still + 1
            if k >= 30 and still >= 5:
                break
        self.pol.sit_mode = False
        self.pol.current_policy = "walking"
        self.pol.ort_session = self.pol.dock_session
        await self.ticks(
            600,
            "backin",
            lambda: (-0.05, 0, self.heading()),
            lambda: self.dk.connected(self.dk.tip_error(self.model, self.data)),
        )
        await self.ticks(100, "charging")
        passed = bool(self.dk.connected(self.dk.tip_error(self.model, self.data)))
        return {
            "verified": passed,
            "message": "仿真触点已对接，虚拟电量已增加" if passed else "触点尚未对接，未记为充电",
            **self.metrics,
        }

    async def close(self):
        await self.stop()
        self.temporary.cleanup()

    async def standing_trial(self, command):
        if command.action == "undock":
            if not self.dk.connected(self.dk.tip_error(self.model, self.data)):
                raise ValueError("当前没有对接，请先完成回窝")
            start = float(self.data.qpos[0])
            released = await self.ticks(
                500, "undock", (0.3, 0, 0), lambda: self.data.qpos[0] > start + 0.08
            )
            await self.ticks(75, "stand")
            return {
                "verified": bool(released and self.upright() > 0.8),
                "message": "按实际脱离接触与站稳状态验收",
                **self.metrics,
            }
        if self.dk.connected(self.dk.tip_error(self.model, self.data)):
            raise ValueError("当前已经对接，请先离窝或重置")
        await self.ticks(40, "look")

        def approach():
            angle = math.degrees(math.atan2(-(self.data.qpos[1] * 1000 + 12), -150))
            return 0.3, 0, self.heading(angle, 0.035, 0.5)

        reached = await self.ticks(1500, "approach", approach, lambda: self.data.qpos[0] <= 0.2405)
        if not reached:
            raise ValueError("未能走到转身位置，已暂停")
        await self.ticks(20, "halt")
        await self.ticks(
            600,
            "turn",
            lambda: (0, 0, np.sign(self.heading())),
            lambda: abs(self.dg.wrap(self.dg.yaw_deg(self.data))) < 10,
        )
        await self.ticks(
            250,
            "align",
            lambda: (
                0,
                0,
                np.sign(self.heading()) * (0.6 if abs(self.dg.yaw_deg(self.data)) > 4 else 0.45),
            ),
            lambda: abs(self.dg.wrap(self.dg.yaw_deg(self.data))) < 1,
        )
        await self.ticks(25, "settle")
        await self.ticks(
            700,
            "backin",
            lambda: (-0.4, 0, self.heading(0, 0.04, 0.4)),
            lambda: self.dk.connected(self.dk.tip_error(self.model, self.data)),
        )
        await self.ticks(100, "charging")
        return {
            "verified": bool(self.dk.connected(self.dk.tip_error(self.model, self.data))),
            "message": "按站姿触点实际对接状态验收，电量为虚拟值",
            **self.metrics,
        }
