"""Passive seesaw: a task policy moves a real duck, never the board joint.

The frozen official gait supplies joint position targets at 50 Hz. Task actions
at 10 Hz select forward/hold/backward; MuJoCo integrates contacts at 200 Hz.
"""

import hashlib
import itertools
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np
import onnxruntime as ort

from .simulation import HOME, Driver

CONTRACT = "seesaw-v4-passive-docking"
DT = 0.1
PIVOT_Z = 0.23
HALF_LENGTH, HALF_WIDTH, HALF_THICKNESS = 0.50, 0.22, 0.015
ANGLE_LIMIT = 0.105
DURATION = 18
OBSERVATION_SIZE = 17
WEIGHT_MASS = 0.28
SLIDER_DAMPING = 1.0
DOCK_HALF_WIDTH = 0.04
DOCK_SPEED = 0.025
DOCK_HOLD = 1.0
VELOCITIES = (0.0, 0.25, -0.35)
REWARD = {
    "level": 0.5,
    "dock": 4.0,
    "brake": 1.0,
    "balance": 1.0,
    "upright": 0.25,
    "turning": 0.1,
    "effort": 0.06,
    "settle": 0.25,
    "switch": 0.03,
    "fall": 15.0,
    "success": 25.0,
}


def build_model(assets: Path):
    directory = assets / "microduck_rl/src/mjlab_microduck/robot/microduck"
    root = ET.parse(directory / "robot_allcollisions.xml").getroot()
    root.find("compiler").set("meshdir", str((directory / "assets").resolve()))
    world = root.find("worldbody")
    ET.SubElement(world, "geom", name="seesaw_floor", type="plane", size="3 3 .1")
    # A fixed pedestal, axle, and a single free hinge. No board actuator/spring.
    base = ET.SubElement(world, "body", name="seesaw_base")
    ET.SubElement(
        base,
        "geom",
        name="seesaw_pedestal",
        type="box",
        pos="0 0 .105",
        size=".045 .18 .105",
        rgba=".28 .33 .31 1",
    )
    ET.SubElement(
        base,
        "geom",
        name="seesaw_axle",
        type="cylinder",
        pos=f"0 0 {PIVOT_Z}",
        size=".021 .25",
        euler="1.57079632679 0 0",
        rgba=".28 .33 .31 1",
        contype="0",
        conaffinity="0",
    )
    board = ET.SubElement(world, "body", name="seesaw_board", pos=f"0 0 {PIVOT_Z}")
    ET.SubElement(
        board,
        "joint",
        name="seesaw_hinge",
        type="hinge",
        axis="0 1 0",
        range=f"{-ANGLE_LIMIT} {ANGLE_LIMIT}",
        damping="10",
    )
    ET.SubElement(
        board,
        "geom",
        name="seesaw_surface",
        type="box",
        size=f"{HALF_LENGTH} {HALF_WIDTH} {HALF_THICKNESS}",
        mass="1.5",
        friction="1 .005 .0001",
        rgba=".75 .79 .69 1",
        condim="3",
    )
    # Paint has neither mass nor collision. Green front (+X), ochre rear (-X).
    for name, x, colour in (
        ("front", 0.365, ".28 .49 .47 1"),
        ("rear", -0.365, ".74 .53 .28 1"),
        ("pivot", 0, ".28 .33 .31 1"),
    ):
        ET.SubElement(
            board,
            "geom",
            name="seesaw_" + name,
            type="box",
            pos=f"{x} 0 .0155",
            size=f"{0.012 if x == 0 else 0.12} .215 .0005",
            mass="0",
            contype="0",
            conaffinity="0",
            rgba=colour,
        )
    # A passive massive slider. Neither it nor the board has an actuator.
    # Duck contact tilts the board; gravity along the rail moves the load.
    ET.SubElement(
        board,
        "geom",
        name="seesaw_rail",
        type="box",
        pos="0 .185 .027",
        size=".39 .012 .009",
        mass="0",
        contype="0",
        conaffinity="0",
        rgba=".24 .29 .31 1",
    )
    weight = ET.SubElement(board, "body", name="seesaw_weight", pos="0 .185 .06")
    ET.SubElement(
        weight,
        "joint",
        name="seesaw_slider",
        type="slide",
        axis="1 0 0",
        range="-.35 .35",
        damping=str(SLIDER_DAMPING),
    )
    ET.SubElement(
        weight,
        "geom",
        name="seesaw_weight_box",
        type="box",
        size=".045 .03 .033",
        mass=str(WEIGHT_MASS),
        rgba=".82 .32 .18 1",
    )
    ET.SubElement(
        weight,
        "geom",
        name="seesaw_weight_stripe",
        type="box",
        pos="0 0 .0335",
        size=".008 .029 .0005",
        mass="0",
        contype="0",
        conaffinity="0",
        rgba=".99 .89 .65 1",
    )
    ET.SubElement(
        board,
        "geom",
        name="seesaw_dock",
        type="box",
        pos="0 .185 .017",
        size=f"{DOCK_HALF_WIDTH} .035 .001",
        mass="0",
        contype="0",
        conaffinity="0",
        rgba=".15 .55 .35 1",
    )
    # Upright painted gate posts make the acceptance interval visible beside the rail.
    for x in (-DOCK_HALF_WIDTH, DOCK_HALF_WIDTH):
        ET.SubElement(
            board,
            "geom",
            name=f"seesaw_dock_{'rear' if x < 0 else 'front'}",
            type="box",
            pos=f"{x} .22 .048",
            size=".003 .003 .03",
            mass="0",
            contype="0",
            conaffinity="0",
            rgba=".15 .55 .35 1",
        )
    xml = ET.tostring(root, encoding="unicode")
    model = mujoco.MjModel.from_xml_string(xml)
    model.opt.timestep = 0.005
    signature = hashlib.sha256(xml.replace(str(directory.resolve()), "ROBOT").encode())
    for file in sorted((directory / "assets").glob("*")):
        signature.update(file.name.encode())
        signature.update(file.read_bytes())
    signature.update((assets / "policies/velstand.onnx").read_bytes())
    return model, signature.hexdigest()


class SeesawWorld:
    def __init__(self, assets, *, compiled=None, session=None):
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
        self.root_v = int(self.model.jnt_dofadr[self.model.joint("trunk_base_freejoint").id])
        self.board = self.model.body("seesaw_board").id
        self.weight_body = self.model.body("seesaw_weight").id
        slider = self.model.joint("seesaw_slider").id
        self.slider_q = int(self.model.jnt_qposadr[slider])
        self.slider_v = int(self.model.jnt_dofadr[slider])
        self.duck_mass = float(self.model.body_subtreemass[self.driver.body])
        joint = self.model.joint("seesaw_hinge").id
        self.hinge_q = int(self.model.jnt_qposadr[joint])
        self.hinge_v = int(self.model.jnt_dofadr[joint])
        self.surface = self.model.geom("seesaw_surface").id
        self.floor = self.model.geom("seesaw_floor").id
        self.feet = [self.model.geom(s + "_foot_collision").id for s in ("left", "right")]
        bodies = [int(self.model.geom_bodyid[g]) for g in self.feet]
        self.support_geoms = {
            g: bodies.index(int(self.model.geom_bodyid[g]))
            for g in self.driver.contact_geoms
            if int(self.model.geom_bodyid[g]) in bodies
        }
        self.foot_bounds = {}
        for g in self.feet:
            mesh = int(self.model.geom_dataid[g])
            start, count = self.model.mesh_vertadr[mesh], self.model.mesh_vertnum[mesh]
            vertices = self.model.mesh_vert[start : start + count]
            self.foot_bounds[g] = np.array(
                list(
                    itertools.product(*zip(vertices.min(axis=0), vertices.max(axis=0), strict=True))
                )
            )
        self.reset(0)

    def reset(self, seed=0):
        if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
            raise ValueError("无效跷跷板种子")
        rng = np.random.default_rng(seed)
        self.seed = seed
        self.start_x = float(rng.choice([-1, 1]) * rng.uniform(0.045, 0.085))
        self.friction = float(rng.uniform(0.85, 1.1))
        self.load_start = float(rng.choice([-1, 1]) * rng.uniform(0.20, 0.24))
        self.model.geom_friction[self.surface, 0] = self.friction
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.driver.root : self.driver.root + 7] = [
            self.start_x,
            0,
            PIVOT_Z + HALF_THICKNESS + 0.125,
            1,
            0,
            0,
            0,
        ]
        self.data.qpos[self.slider_q] = self.load_start
        self.data.qpos[self.driver.q] = HOME
        self.data.ctrl[self.driver.ids] = HOME
        self.driver.command[:] = self.driver.last[:] = 0
        self.command = np.zeros(3)
        self.last_action = 0
        self.done, self.reason = False, None
        self.hold = self.contact_gap = self.level_sum = 0.0
        self.balanced_ticks = self.scored_ticks = 0
        self.steps = 0
        self.reward_terms = dict.fromkeys(REWARD, 0.0)
        mujoco.mj_forward(self.model, self.data)
        return self.observation()

    def measure(self):
        m, d = self.model, self.data
        pos, yaw = self.driver.pose(d)
        rotation = d.xmat[self.board].reshape(3, 3)
        local = rotation.T @ (pos - d.xpos[self.board])
        contacts, body_contact, ground_contact, torque = set(), False, False, 0.0
        force = np.zeros(6)
        for i, c in enumerate(d.contact):
            pair = {int(c.geom1), int(c.geom2)}
            if self.floor in pair and pair & self.driver.contact_geoms:
                ground_contact = True
            other = next(iter(pair - {self.surface}), -1)
            if self.surface not in pair or other not in self.driver.contact_geoms:
                continue
            if other in self.support_geoms:
                contacts.add(self.support_geoms[other])
            else:
                body_contact = True
            # mj_contactForce acts on geom2 in the contact frame. Resolve the
            # force on the board, then take its moment about world +Y axle.
            mujoco.mj_contactForce(m, d, i, force)
            on_board = c.frame.reshape(3, 3).T @ force[:3]
            if int(c.geom1) == self.surface:
                on_board = -on_board
            torque += float(np.cross(c.pos - d.xpos[self.board], on_board)[1])
        margin = HALF_WIDTH
        for g in self.feet:
            points = self.foot_bounds[g] @ d.geom_xmat[g].reshape(3, 3).T
            points = (points + d.geom_xpos[g] - d.xpos[self.board]) @ rotation
            margin = min(
                margin,
                HALF_LENGTH - float(abs(points[:, 0]).max()),
                HALF_WIDTH - float(abs(points[:, 1]).max()),
            )
        pivot = d.xpos[self.board]
        weight_torque = WEIGHT_MASS * 9.81 * (d.xipos[self.weight_body, 0] - pivot[0])
        duck_torque = self.duck_mass * 9.81 * (d.subtree_com[self.driver.body, 0] - pivot[0])
        return {
            "position_m": float(local[0]),
            "lateral_m": float(local[1]),
            "height_m": float(local[2] - HALF_THICKNESS),
            "angle_deg": math.degrees(float(d.qpos[self.hinge_q])),
            "angular_speed_deg_s": math.degrees(float(d.qvel[self.hinge_v])),
            "contact_torque_nm": torque,
            "contacts": len(contacts),
            "body_contact": body_contact,
            "ground_contact": ground_contact,
            "upright": float(d.xmat[self.driver.body].reshape(3, 3)[2, 2]),
            "heading_rad": yaw,
            "edge_margin_m": margin,
            "weight_position_m": float(d.qpos[self.slider_q]),
            "weight_velocity_m_s": float(d.qvel[self.slider_v]),
            "dock_position_m": 0.0,
            "dock_error_m": float(d.qpos[self.slider_q]),
            "dock_half_width_m": DOCK_HALF_WIDTH,
            "dock_hold_seconds": self.hold,
            "weight_actuators": 0,
            "weight_gravity_torque_nm": float(weight_torque),
            "net_gravity_torque_nm": float(weight_torque + duck_torque),
            "balance_fraction": self.balanced_ticks / max(1, self.scored_ticks),
        }

    def observation(self, measured=None):
        p = measured if measured is not None else self.measure()
        velocity = self.data.qvel[self.root_v : self.root_v + 2]
        return np.array(
            [
                p["position_m"] / 0.1,
                p["lateral_m"] / 0.1,
                velocity[0] / 0.25,
                velocity[1] / 0.15,
                p["heading_rad"] / 0.4,
                p["upright"],
                p["angle_deg"] / 6,
                p["angular_speed_deg_s"] / 12,
                p["contacts"] / 2,
                *[float(self.last_action == i) for i in range(3)],
                min(self.hold / DOCK_HOLD, 1),
                self.steps / (DURATION / DT),
                p["weight_position_m"] / 0.32,
                p["weight_velocity_m_s"] / 0.25,
                p["net_gravity_torque_nm"],
            ],
            np.float32,
        )

    @staticmethod
    def rule_action(obs):
        # An honest, untrained engineering comparison, never called PPO.
        error = obs[16] / (0.73724318 * 9.81) + 0.4 * math.radians(obs[6] * 6)
        return 2 if error > 0.015 else 1 if error < -0.015 else 0

    @staticmethod
    def center_action(obs):
        # Explicitly ignores the load and board angle: the former easy solution.
        return 2 if obs[0] * 0.1 > 0.008 else 1 if obs[0] * 0.1 < -0.008 else 0

    def step(self, action):
        if self.done:
            raise RuntimeError("本轮已结束，请重置")
        if isinstance(action, np.integer):
            action = int(action)
        if type(action) is not int or action not in range(3):
            raise ValueError("跷跷板动作必须为站定、前进或后退")
        _, yaw = self.driver.pose(self.data)
        self.command[:] = [
            VELOCITIES[action],
            np.clip(-2 * self.data.qpos[self.driver.root + 1], -0.06, 0.06),
            np.clip(-3 * yaw, -0.8, 0.8),
        ]
        before = float(self.data.time)
        for _ in range(5):
            self.driver.command[:3] = self.command
            self.driver.step(self.model, self.data)
            for _ in range(4):
                mujoco.mj_step(self.model, self.data)
            mujoco.mj_forward(self.model, self.data)
        if (
            not np.isfinite(self.data.qpos).all()
            or not np.isfinite(self.data.qvel).all()
            or abs(float(self.data.time) - before - DT) > 1e-7
        ):
            raise FloatingPointError("跷跷板物理状态或时钟异常，已暂停")
        changed = action != self.last_action
        self.last_action, self.steps = action, self.steps + 1
        p = self.measure()
        self.contact_gap = self.contact_gap + DT if not p["contacts"] else 0
        fallen = (
            p["upright"] < 0.65
            or p["height_m"] < 0.075
            or p["body_contact"]
            or p["ground_contact"]
            or self.contact_gap > 0.4
            or p["edge_margin_m"] < 0
        )
        level = abs(p["angle_deg"]) < 2 and abs(p["angular_speed_deg_s"]) < 4
        stable = level and p["contacts"] > 0
        docked = (
            stable
            and abs(p["dock_error_m"]) < DOCK_HALF_WIDTH
            and abs(p["weight_velocity_m_s"]) < DOCK_SPEED
        )
        self.hold = self.hold + DT if docked else 0
        p["dock_hold_seconds"] = self.hold
        if self.steps > 2 / DT:
            self.scored_ticks += 1
            self.balanced_ticks += int(stable)
        p["balance_fraction"] = self.balanced_ticks / max(1, self.scored_ticks)
        self.level_sum += abs(p["angle_deg"])
        timed_out = self.steps >= DURATION / DT
        self.done = bool(fallen or timed_out)
        success = bool(timed_out and not fallen and self.hold >= DOCK_HOLD - 1e-6)
        self.reason = (
            "fell_or_left_board"
            if fallen
            else ("success" if success else "not_docked" if timed_out else None)
        )
        self.reward_terms = {
            "dock": REWARD["dock"] * math.exp(-((p["dock_error_m"] / 0.12) ** 2)),
            "brake": REWARD["brake"]
            * math.exp(
                -((p["dock_error_m"] / 0.06) ** 2) - ((p["weight_velocity_m_s"] / 0.05) ** 2)
            ),
            "level": REWARD["level"] * math.exp(-((p["angle_deg"] / 3) ** 2)),
            "balance": REWARD["balance"] * math.exp(-((p["net_gravity_torque_nm"] / 0.35) ** 2)),
            "upright": REWARD["upright"] * p["upright"],
            "turning": -REWARD["turning"] * min(abs(p["angular_speed_deg_s"]) / 12, 2),
            "effort": -REWARD["effort"] * int(action != 0),
            "settle": REWARD["settle"] * int(docked and action == 0),
            "switch": -REWARD["switch"] * int(changed),
            "fall": -REWARD["fall"] * int(fallen or timed_out and not success),
            "success": REWARD["success"] * int(success),
        }
        info = {
            **p,
            "seconds": float(self.data.time),
            "success": success,
            "reason": self.reason,
            "hold_seconds": self.hold,
            "mean_abs_angle_deg": self.level_sum / self.steps,
            "reward_terms": self.reward_terms.copy(),
        }
        return self.observation(p), sum(self.reward_terms.values()), self.done, False, info

    def manifest(self):
        return {
            "contract": CONTRACT,
            "model_sha256": self.fingerprint,
            "observation_size": OBSERVATION_SIZE,
            "action_size": 3,
            "action_type": "categorical",
            "velocities_m_s": VELOCITIES,
            "duration_seconds": DURATION,
            "physics_hz": 200,
            "gait_hz": 50,
            "task_hz": 10,
            "board_actuators": 0,
            "weight_actuators": 0,
            "weight_mass_kg": WEIGHT_MASS,
            "weight_start_abs_m": [0.20, 0.24],
            "slider_damping_n_s_m": SLIDER_DAMPING,
            "dock_position_m": 0.0,
            "dock_half_width_m": DOCK_HALF_WIDTH,
            "dock_max_speed_m_s": DOCK_SPEED,
            "dock_hold_seconds": DOCK_HOLD,
            "success": (
                "18s no fall; final 1s load within center +/-4cm, |load speed|<2.5cm/s; "
                "supported, |angle|<2deg, |angular speed|<4deg/s"
            ),
            "hinge_damping_nm_s": 10,
            "reward": REWARD,
            "observation_source": "MuJoCo ground truth, not camera vision",
            "prior": "lateral/heading feedback; frozen official gait; discrete speeds",
        }
