"""Interactive turntable battle-royale scene: a real motorized disk game.

The disk is a true velocity-actuated body (explicit small mass + gravity
compensation so its own floor friction cannot eat the motor torque; disk
friction wins over duck feet via geom priority). Ducks ride it by friction —
sitstand "stand" statues are carried around, seated ducks slide like curling
stones. Elimination is measured per physics tick: a trunk actually crossing
the rim leaves the table. Nothing about survival is scripted.
"""

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco

MEMBERS = "abcd"
DISK_R = 1.02
SPAWNS = [(0.5 * math.cos(i * math.tau / 4), 0.5 * math.sin(i * math.tau / 4))
          for i in range(4)]  # mid-radius start; closer to the center is safer
SPIN_SPEEDS = {"spin_stop": 0.0, "spin_slow": 1.2, "spin_medium": 2.4, "spin_fast": 4.0}


def _decor():
    """Roulette spokes, rim dots and tangential arrows riding the disk body."""
    parts = []
    for i in range(4):  # bold tangential arrows: rotation direction at a glance
        a = i * math.tau / 4 + 0.35
        cx, cy = 0.86 * math.cos(a), 0.86 * math.sin(a)
        for k, off in enumerate((-0.055, 0.055)):
            b = a + math.pi / 2 + k * 0.5 - 0.25
            parts.append(
                f'<geom name="arrow{i}_{k}" type="box" '
                f'pos="{cx + off * math.cos(a + math.pi / 2):.3f} '
                f'{cy + off * math.sin(a + math.pi / 2):.3f} .03" '
                f'quat="{math.cos(b / 2):.4f} 0 0 {math.sin(b / 2):.4f}" '
                f'size=".13 .02 .004" rgba=".08 .08 .08 1" contype="0" '
                f'conaffinity="0" group="2"/>')
    for i in range(6):  # alternating spokes
        a = i * math.tau / 6
        rgba = ".98 .94 .88" if i % 2 == 0 else ".82 .28 .22"
        parts.append(
            f'<geom name="spoke{i}" type="box" '
            f'pos="{0.48 * math.cos(a):.3f} {0.48 * math.sin(a):.3f} .027" '
            f'quat="{math.cos(a / 2):.4f} 0 0 {math.sin(a / 2):.4f}" size=".43 .07 .004" '
            f'rgba="{rgba} 1" contype="0" conaffinity="0" group="2"/>')
    for i in range(10):  # rim dots
        a = i * math.tau / 10
        rgba = ".98 .94 .88" if i % 2 == 0 else ".82 .28 .22"
        parts.append(
            f'<geom name="dot{i}" type="sphere" '
            f'pos="{0.93 * math.cos(a):.3f} {0.93 * math.sin(a):.3f} .03" size=".035" '
            f'rgba="{rgba} 1" contype="0" conaffinity="0" group="2"/>')
    return "".join(parts)


def build_turntable_scene(robot_dir: Path):
    spec = mujoco.MjSpec.from_string(
        '<mujoco><worldbody>'
        '<geom name="floor" type="plane" size="6 6 .1" rgba=".3 .68 .28 1"/>'
        '<body name="turntable" pos="0 0 0.02" gravcomp="1">'
        '<joint name="spin" type="hinge" axis="0 0 1" pos="0 0 0"/>'
        '<geom name="disk" type="cylinder" size="1.05 .02" mass="12" '
        'rgba=".72 .5 .3 1" friction=".6 .008 .0008" priority="1"/>'
        '<geom name="rim" type="cylinder" size="1.06 .028" rgba=".5 .32 .18 1" '
        'mass="0" contype="0" conaffinity="0" group="2"/>'
        + _decor() +
        '</body></worldbody>'
        '<actuator><velocity name="spinner" joint="spin" kv="40"/></actuator></mujoco>')
    for member in MEMBERS:
        from .grasp_model import articulate_mouth

        root = ET.parse(Path(robot_dir) / "robot_allcollisions.xml").getroot()
        root.find("compiler").set("meshdir", str((Path(robot_dir) / "assets").resolve()))
        articulate_mouth(root)
        robot = mujoco.MjSpec.from_string(ET.tostring(root, encoding="unicode"))
        spec.attach(robot, prefix=member + "_", frame=spec.worldbody.add_frame())
    model = spec.compile()
    model.opt.timestep = 0.005
    return model


class TurntableGame:
    """Per-tick spin control and measured elimination bookkeeping."""

    def __init__(self, backend):
        self.b = backend
        self.spinner = backend.model.actuator("spinner").id
        self.spin_q = backend.model.jnt_qposadr[backend.model.joint("spin").id]
        self.spin_v = backend.model.jnt_dofadr[backend.model.joint("spin").id]
        self.target = 0.0
        self.eliminated = []  # [{"member", "at_s", "radial_m", "omega"}]
        self.out = [False] * 4

    def set_spin(self, action_name):
        self.target = SPIN_SPEEDS[action_name]
        return {
            "verified": True,
            "spin": action_name,
            "target_omega": self.target,
            "rim_speed_mps": round(self.target * DISK_R, 2),
        }

    def tick(self):
        b = self.b
        b.data.ctrl[self.spinner] = self.target
        omega = float(b.data.qvel[self.spin_v])
        elapsed = float(b.data.time)
        for i, d in enumerate(b.drivers):
            if self.out[i]:
                continue
            pos = d.pose(b.data)[0]
            radius = math.hypot(pos[0], pos[1])
            if radius > DISK_R:
                self.out[i] = True
                self.eliminated.append({
                    "member": MEMBERS[i],
                    "at_s": round(elapsed, 2),
                         "radial_m": round(radius, 6),
                    "omega": round(abs(omega), 2),
                })
        standing = [
            i for i in range(4)
            if not self.out[i] and float(b.data.xmat[b.drivers[i].body, 8]) > 0.94
        ]
        self.remaining = standing

    def snapshot(self):
        omega = float(self.b.data.qvel[self.spin_v])
        ducks = []
        for i, d in enumerate(self.b.drivers):
            pos = d.pose(self.b.data)[0]
            ducks.append({
                "member": MEMBERS[i],
                "out": self.out[i],
                "radius_m": round(math.hypot(pos[0], pos[1]), 3),
                "upright": round(float(self.b.data.xmat[d.body, 8]), 2),
            })
        return {
            "angle": round(float(self.b.data.qpos[self.spin_q]), 3),
            "omega": round(omega, 2),
            "target_omega": self.target,
            "rim_speed_mps": round(abs(omega) * DISK_R, 2),
            "eliminated": list(self.eliminated),
            "remaining": len([d for d in ducks if not d["out"]]),
            "ducks": ducks,
            "source": "real_velocity_actuator_measured_eliminations",
        }
