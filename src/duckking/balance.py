"""Shared CPU physics for training and live voice balance coaching.

The learned controller commands the frozen official gait at 10 Hz. It does not
apply forces to the robot or rewrite its pose. The same engine runs in both paths.
"""

import hashlib
import itertools
import math
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

import mujoco
import numpy as np
import onnxruntime as ort

from .simulation import HOME, POLICY_JOINTS, Driver

CONTRACT = "balance-v4-gain-bodyframe"
DT = 0.1
RADIUS = 0.36
TOP = 0.22
LEVELS = {
    1: {"title": "跟着圆盘站稳", "rpm": 9.0, "tilt_deg": 3.0, "offset": 0.025},
    2: {"title": "转盘转，我不转", "rpm": 12.0, "tilt_deg": 4.0, "offset": 0.025},
    3: {"title": "从边缘回到中心", "rpm": 10.0, "tilt_deg": 5.0, "offset": 0.16},
}
REWARD = {
    "upright": 1.0,
    "center": 2.0,
    "heading": 1.0,
    "progress": 8.0,
    "slip": 0.15,
    "smooth": 0.025,
    "fall": 10.0,
    "success": 20.0,
}


@dataclass(frozen=True)
class BalanceConfig:
    level: int = 1
    challenge_seconds: float = 10.0
    stop_seconds: float = 3.0
    difficulty: float = 1.0

    def __post_init__(self):
        if self.level not in LEVELS or not 0 <= self.difficulty <= 1:
            raise ValueError("无效关卡或难度")
        if not 3 <= self.challenge_seconds <= 30 or not 3 <= self.stop_seconds <= 10:
            raise ValueError("挑战时长必须有界并保留至少 3 秒减速")


def point_velocity(model, data, body, point):
    """Velocity at a world point on a body, referenced to the regular body frame.

    mjOBJ_BODY is the inertial/COM frame; mjOBJ_XBODY is xpos/xmat. Pairing
    mjOBJ_BODY velocity with an xpos moment arm would count the wrong offset.
    """
    velocity = np.zeros(6)
    mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_XBODY, body, velocity, 0)
    return velocity[3:] + np.cross(velocity[:3], point - data.xpos[body])


def build_model(assets: Path):
    directory = assets / "microduck_rl/src/mjlab_microduck/robot/microduck"
    root = ET.parse(directory / "robot_allcollisions.xml").getroot()
    root.find("compiler").set("meshdir", str((directory / "assets").resolve()))
    world = root.find("worldbody")
    ET.SubElement(
        world, "geom", name="balance_floor", type="plane", size="3 3 .1", rgba=".83 .87 .78 1"
    )
    base = ET.SubElement(world, "body", name="balance_base", pos=f"0 0 {TOP - 0.025}")
    ET.SubElement(
        base,
        "geom",
        type="cylinder",
        size=".09 .09",
        pos="0 0 -.09",
        rgba=".26 .31 .35 1",
        contype="0",
        conaffinity="0",
    )
    parent = base
    for name, axis in [("roll", "1 0 0"), ("pitch", "0 1 0"), ("spin", "0 0 1")]:
        parent = ET.SubElement(parent, "body", name="disc_" + name)
        ET.SubElement(parent, "inertial", pos="0 0 0", mass=".1", diaginertia=".002 .002 .002")
        ET.SubElement(
            parent,
            "joint",
            name="disc_" + name,
            type="hinge",
            axis=axis,
            damping=".05",
            armature=".001",
            limited="false" if name == "spin" else "true",
            **({} if name == "spin" else {"range": "-.18 .18"}),
        )
    # A massive, torque-driven disk. Stripes have no collision and move with it.
    parent.remove(parent.find("inertial"))
    ET.SubElement(
        parent,
        "geom",
        name="disc_surface",
        type="cylinder",
        size=f"{RADIUS} .025",
        mass="2",
        rgba=".16 .34 .46 1",
        friction="1 .005 .0001",
        condim="3",
    )
    for i in range(8):
        a = i * math.pi / 4
        ET.SubElement(
            parent,
            "geom",
            name=f"disc_stripe_{i}",
            type="box",
            pos=f"{0.24 * math.cos(a)} {0.24 * math.sin(a)} .0255",
            size=".085 .004 .0005",
            euler=f"0 0 {a}",
            mass=".0001",
            rgba=".74 .85 .87 1",
            contype="0",
            conaffinity="0",
        )
    actuator = root.find("actuator")
    for name in ("roll", "pitch"):
        ET.SubElement(
            actuator,
            "position",
            name="disc_" + name,
            joint="disc_" + name,
            kp="120",
            kv="10",
            forcerange="-25 25",
            ctrlrange="-.15 .15",
        )
    ET.SubElement(
        actuator,
        "velocity",
        name="disc_spin",
        joint="disc_spin",
        kv="8",
        forcerange="-12 12",
        ctrlrange="-2 2",
    )
    xml = ET.tostring(root, encoding="unicode")
    model = mujoco.MjModel.from_xml_string(xml)
    model.opt.timestep = 0.005
    # Exclude the absolute local asset directory from the portable model fingerprint.
    signature = hashlib.sha256(xml.replace(str(directory.resolve()), "ROBOT").encode())
    for file in sorted((directory / "assets").glob("*")):
        signature.update(file.name.encode())
        signature.update(file.read_bytes())
    signature.update((assets / "policies/velstand.onnx").read_bytes())
    return model, signature.hexdigest()


class BalanceWorld:
    """No wall clock and no renderer: 200 Hz physics, 50 Hz gait, 10 Hz task PPO."""

    def __init__(self, assets: Path, config=None, compiled=None, session=None):
        self.config = config or BalanceConfig()
        self.model, self.fingerprint = compiled or build_model(assets)
        self.data = mujoco.MjData(self.model)
        if session is None:
            options = ort.SessionOptions()
            options.intra_op_num_threads = options.inter_op_num_threads = 1
            session = ort.InferenceSession(
                str(assets / "policies/velstand.onnx"), options, providers=["CPUExecutionProvider"]
            )
        self.session = session
        self.driver = Driver(self.model, "", {"walk": session})
        self.disc = self.model.body("disc_spin").id
        self.surface = self.model.geom("disc_surface").id
        self.floor = self.model.geom("balance_floor").id
        self.disc_act = [self.model.actuator("disc_" + s).id for s in ("roll", "pitch", "spin")]
        joints = [self.model.joint("disc_" + s).id for s in ("roll", "pitch", "spin")]
        self.disc_q = self.model.jnt_qposadr[joints]
        self.disc_v = self.model.jnt_dofadr[joints]
        self.feet = [self.model.geom(s + "_foot_collision").id for s in ("left", "right")]
        foot_bodies = [int(self.model.geom_bodyid[g]) for g in self.feet]
        self.support_geoms = {
            g: foot_bodies.index(int(self.model.geom_bodyid[g]))
            for g in self.driver.contact_geoms
            if int(self.model.geom_bodyid[g]) in foot_bodies
        }
        self.foot_bounds = {}
        for geom in self.feet:
            mesh = int(self.model.geom_dataid[geom])
            start, count = self.model.mesh_vertadr[mesh], self.model.mesh_vertnum[mesh]
            vertices = self.model.mesh_vert[start : start + count]
            self.foot_bounds[geom] = np.array(
                list(
                    itertools.product(*zip(vertices.min(axis=0), vertices.max(axis=0), strict=True))
                )
            )
        self.reset(0)

    def reset(self, seed):
        rng = np.random.default_rng(seed)
        mujoco.mj_resetData(self.model, self.data)
        self.seed = int(seed)
        self.phase = rng.uniform(0, 2 * math.pi, 3)
        self.direction = rng.choice([-1, 1])
        self.friction = float(rng.uniform(0.8, 1.1))
        # Model is shared only within this world's serialized train/eval execution.
        self.model.geom_friction[self.surface, 0] = self.friction
        r = LEVELS[self.config.level]["offset"] * rng.uniform(0.75, 1.0)
        a = rng.uniform(0, math.tau)
        yaw = rng.uniform(-0.12, 0.12)
        self.data.qpos[self.driver.root : self.driver.root + 7] = [
            r * math.cos(a),
            r * math.sin(a),
            TOP + 0.125,
            math.cos(yaw / 2),
            0,
            0,
            math.sin(yaw / 2),
        ]
        self.data.qpos[self.driver.q] = HOME
        self.data.ctrl[self.driver.ids] = HOME
        self.driver.last[:] = 0
        self.driver.command[:] = 0
        self.last_action = np.zeros(3, np.float32)
        self.command = np.zeros(3)
        self.target = np.zeros(3)
        self.stop_at = None
        self.done = False
        self.reason = None
        self.steps = 0
        self.contact_gap = 0.0
        self.center_hold = 0.0
        self.heading_good = 0
        self.max_radius = 0.0
        self.sum_slip = 0.0
        self.reward_terms = dict.fromkeys(REWARD, 0.0)
        mujoco.mj_forward(self.model, self.data)
        self.previous_distance = self.measure()["radius"]
        return self.observation()

    def request_stop(self):
        if self.stop_at is None:
            self.stop_at = float(self.data.time)

    def _drive_disc(self):
        t = float(self.data.time)
        stopping = self.stop_at if self.stop_at is not None else self.config.challenge_seconds
        envelope = min(1.0, t / 1.5) * max(0.0, 1.0 - max(0.0, t - stopping) / 1.5)
        level = LEVELS[self.config.level]
        amplitude = math.radians(level["tilt_deg"]) * self.config.difficulty * envelope
        desired = np.array(
            [
                amplitude * math.sin(0.7 * t + self.phase[0]),
                amplitude * math.sin(0.53 * t + self.phase[1]),
                level["rpm"]
                * math.tau
                / 60
                * self.config.difficulty
                * envelope
                * self.direction
                * (0.7 + 0.3 * math.sin(0.8 * t + self.phase[2])),
            ]
        )
        # Limit rates even if the user requests stop halfway through a challenge.
        rate = np.array([0.12, 0.12, 1.2]) * self.model.opt.timestep
        self.target += np.clip(desired - self.target, -rate, rate)
        self.data.ctrl[self.disc_act] = self.target

    def measure(self):
        d, m = self.data, self.model
        pos, yaw = self.driver.pose(d)
        rotation = d.xmat[self.disc].reshape(3, 3)
        local = rotation.T @ (pos - d.xpos[self.disc])
        contacts, slip, body_contact = set(), [], False
        for c in d.contact:
            pair = {int(c.geom1), int(c.geom2)}
            other = next(iter(pair - {self.surface}), -1)
            if self.floor in pair and pair & self.driver.contact_geoms:
                body_contact = True
            if self.surface not in pair or other not in self.driver.contact_geoms:
                continue
            if other not in self.support_geoms:
                body_contact = True
                continue
            contacts.add(self.support_geoms[other])
            body = int(m.geom_bodyid[other])
            vf = point_velocity(m, d, body, c.pos)
            vd = point_velocity(m, d, self.disc, c.pos)
            relative = rotation.T @ (vf - vd)
            slip.append(float(np.linalg.norm(relative[:2])))
        # Bound the whole foot by its actual mesh vertices, not just torso position.
        rim = RADIUS
        for geom in self.feet:
            vertices = self.foot_bounds[geom] @ d.geom_xmat[geom].reshape(3, 3).T
            vertices = (vertices + d.geom_xpos[geom] - d.xpos[self.disc]) @ rotation
            rim = min(rim, RADIUS - float(np.max(np.linalg.norm(vertices[:, :2], axis=1))))
        return {
            "radius": float(np.linalg.norm(local[:2])),
            "height": float(local[2] - 0.025),
            "upright": float(d.xmat[self.driver.body].reshape(3, 3)[2, 2]),
            "heading_error": math.atan2(math.sin(yaw), math.cos(yaw)),
            "contacts": len(contacts),
            "slip": float(np.mean(slip)) if slip else 0.0,
            "rim_margin": rim,
            "body_contact": body_contact,
            "rpm": float(d.qvel[self.disc_v[2]]) * 60 / math.tau,
            "tilt_deg": np.rad2deg(d.qpos[self.disc_q[:2]]).tolist(),
        }

    def observation(self, measured=None):
        d = self.data
        pos, yaw = self.driver.pose(d)
        c, s = math.cos(yaw), math.sin(yaw)
        xy = pos[:2]
        goal = np.array([-c * xy[0] - s * xy[1], s * xy[0] - c * xy[1]]) / 0.10
        velocity = np.zeros(6)
        mujoco.mj_objectVelocity(
            self.model, d, mujoco.mjtObj.mjOBJ_XBODY, self.driver.body, velocity, 1
        )
        measured = measured if measured is not None else self.measure()
        return np.concatenate(
            [
                goal,
                [math.sin(yaw), math.cos(yaw)],
                -d.xmat[self.driver.body].reshape(3, 3)[2, :],
                velocity,
                d.qpos[self.disc_q[:2]],
                d.qvel[self.disc_v],
                [measured["contacts"] / 2, measured["height"] / 0.15],
                self.last_action,
                [
                    float(d.time) / (self.config.challenge_seconds + self.config.stop_seconds),
                    float(self.stop_at is not None or d.time >= self.config.challenge_seconds),
                ],
            ]
        ).astype(np.float32)

    def step(self, action):
        if self.done:
            raise RuntimeError("本轮已结束，请重置")
        action = np.asarray(action, dtype=np.float32)
        if action.shape != (3,) or not np.isfinite(action).all():
            raise ValueError("策略返回了无效动作")
        action = np.clip(action, -1, 1)
        smooth = float(np.mean((action - self.last_action) ** 2))
        # CPU-first educational task: PPO learns bounded feedback strengths,
        # not arbitrary velocity directions. The centering/heading feedback law
        # is an explicit engineering prior, separately exposed in the UI.
        gains = np.maximum(action, 0)
        obs = self.observation()
        yaw = math.atan2(obs[2], obs[3])
        desired = np.clip(
            [
                gains[0] * 3 * obs[0] * 0.10,
                gains[1] * 3 * obs[1] * 0.10,
                -gains[2] * (4 * yaw + 1.5 * self.data.qvel[self.disc_v[2]])
                if self.config.level >= 2
                else 0.0,
            ],
            [-0.18, -0.12, -1.8],
            [0.18, 0.12, 1.8],
        )
        time_before = float(self.data.time)
        self.command += np.clip(desired - self.command, [-0.08, -0.06, -0.6], [0.08, 0.06, 0.6])
        for _ in range(5):
            self.driver.command[:3] = self.command
            self.driver.step(self.model, self.data)
            self.data.ctrl[self.driver.ids] = np.clip(self.data.ctrl[self.driver.ids], -10, 10)
            for _ in range(4):
                self._drive_disc()
                mujoco.mj_step(self.model, self.data)
            # Training and deployment both sample freshly forwarded state at 50 Hz.
            mujoco.mj_forward(self.model, self.data)
        if not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all():
            raise FloatingPointError("MuJoCo 状态无效")
        if abs(float(self.data.time) - time_before - DT) > 1e-7:
            raise FloatingPointError("MuJoCo 时钟异常，可能发生数值重置；本轮已终止")
        self.last_action[:] = action
        self.steps += 1
        measured = self.measure()
        self.max_radius = max(self.max_radius, measured["radius"])
        self.contact_gap = self.contact_gap + DT if measured["contacts"] == 0 else 0.0
        self.sum_slip += measured["slip"]
        centered = measured["radius"] < 0.08
        self.center_hold = self.center_hold + DT if centered else 0.0
        self.heading_good += int(abs(measured["heading_error"]) < math.radians(25))
        fallen = (
            measured["upright"] < 0.65
            or measured["height"] < 0.075
            or measured["body_contact"]
            or self.contact_gap > 0.4
            or measured["rim_margin"] < 0
        )
        self.reward_terms = {
            "upright": REWARD["upright"] * measured["upright"],
            "center": REWARD["center"] * math.exp(-((measured["radius"] / 0.10) ** 2)),
            "heading": REWARD["heading"] * math.exp(-((measured["heading_error"] / 0.35) ** 2))
            if self.config.level >= 2
            else 0.0,
            "progress": REWARD["progress"] * (self.previous_distance - measured["radius"]) / DT,
            "slip": -REWARD["slip"] * measured["slip"],
            "smooth": -REWARD["smooth"] * smooth,
            "fall": -REWARD["fall"] if fallen else 0.0,
        }
        self.previous_distance = measured["radius"]
        stopping = self.stop_at if self.stop_at is not None else self.config.challenge_seconds
        timed_out = self.data.time >= stopping + self.config.stop_seconds - 1e-6
        self.done = bool(fallen or timed_out)
        stopped = abs(measured["rpm"]) < 0.25 and max(abs(v) for v in measured["tilt_deg"]) < 1
        success = bool(
            timed_out
            and not fallen
            and stopped
            and self.center_hold >= 1.0
            and (self.config.level == 1 or self.heading_good / self.steps >= 0.85)
            and self.stop_at is None
        )
        self.reward_terms["success"] = REWARD["success"] if success else 0.0
        if timed_out and not success and self.stop_at is None:
            self.reward_terms["fall"] = -REWARD["fall"]
        self.reason = (
            "fell_or_left_disc"
            if fallen
            else "cancelled"
            if self.stop_at is not None
            else "success"
            if success
            else "criteria_not_met"
            if timed_out
            else None
        )
        info = {
            **measured,
            "success": success,
            "reason": self.reason,
            "reward_terms": self.reward_terms.copy(),
            "seconds": float(self.data.time),
            "center_hold": self.center_hold,
            "heading_fraction": self.heading_good / self.steps,
            "mean_slip": self.sum_slip / self.steps,
            "disk_stopped": stopped,
        }
        return (
            self.observation(measured),
            float(sum(self.reward_terms.values())),
            self.done,
            False,  # The finite challenge is terminal, not an external TimeLimit cut.
            info,
        )

    def manifest(self):
        return {
            "contract": CONTRACT,
            "model_sha256": self.fingerprint,
            "config": asdict(self.config),
            "joints": list(POLICY_JOINTS),
            "physics_hz": 200,
            "gait_hz": 50,
            "ppo_hz": 10,
            "observation_size": len(self.observation()),
            "goal_observation_scale_m": 0.10,
            "action_size": 3,
            "action_scale": [0.18, 0.12, 1.8],
            "reward": REWARD,
            "reward_version": 2,
            "controller": "PPO feedback gains + explicit centering law + frozen official gait",
            "feedback": {
                "xy_gain_max": 3.0,
                "heading_gain_max": 4.0,
                "spin_feedforward_max": 1.5,
                "action_map": "gain=max(action,0), action in [-1,1]",
            },
            "observation_source": "MuJoCo ground truth, not camera vision",
        }
