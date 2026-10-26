"""Interactive turntable battle-royale scene with measured recovery."""

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco

MEMBERS = "abcd"
DISK_R = 1.02
SPAWNS = [(0.5 * math.cos(i * math.tau / 4), 0.5 * math.sin(i * math.tau / 4)) for i in range(4)]
SPIN_SPEEDS = {"spin_stop": 0.0, "spin_slow": 1.2, "spin_medium": 2.4, "spin_fast": 4.0}
DUCK_COLORS = {"a": "red", "b": "blue", "c": "green", "d": "yellow"}
DUCK_RGBA = {
    "a": (1.0, 0.0, 0.0, 1.0),
    "b": (0.0, 0.2, 1.0, 1.0),
    "c": (0.0, 0.9, 0.2, 1.0),
    "d": (1.0, 0.85, 0.0, 1.0),
}


def _decor():
    parts = []
    for i in range(4):
        a = i * math.tau / 4 + 0.35
        cx, cy = 0.86 * math.cos(a), 0.86 * math.sin(a)
        for k, off in enumerate((-0.055, 0.055)):
            b = a + math.pi / 2 + k * 0.5 - 0.25
            parts.append(
                f'<geom name="arrow{i}_{k}" type="box" '
                f'pos="{cx + off * math.cos(a + math.pi / 2):.3f} '
                f'{cy + off * math.sin(a + math.pi / 2):.3f} .03" '
                f'quat="{math.cos(b / 2):.4f} 0 0 {math.sin(b / 2):.4f}" '
                'size=".13 .02 .004" rgba=".08 .08 .08 1" '
                'contype="0" conaffinity="0" group="2"/>'
            )
    for i in range(6):
        a = i * math.tau / 6
        rgba = ".98 .94 .88" if i % 2 == 0 else ".82 .28 .22"
        parts.append(
            f'<geom name="spoke{i}" type="box" '
            f'pos="{0.48 * math.cos(a):.3f} {0.48 * math.sin(a):.3f} .027" '
            f'quat="{math.cos(a / 2):.4f} 0 0 {math.sin(a / 2):.4f}" '
            f'size=".43 .07 .004" rgba="{rgba} 1" '
            'contype="0" conaffinity="0" group="2"/>'
        )
    for i in range(10):
        a = i * math.tau / 10
        rgba = ".98 .94 .88" if i % 2 == 0 else ".82 .28 .22"
        parts.append(
            f'<geom name="dot{i}" type="sphere" '
            f'pos="{0.93 * math.cos(a):.3f} {0.93 * math.sin(a):.3f} .03" '
            f'size=".035" rgba="{rgba} 1" '
            'contype="0" conaffinity="0" group="2"/>'
        )
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
        + _decor()
        + '</body></worldbody><actuator>'
        '<velocity name="spinner" joint="spin" kv="40"/></actuator></mujoco>'
    )
    for member in MEMBERS:
        from .grasp_model import articulate_mouth

        root = ET.parse(Path(robot_dir) / "robot_allcollisions.xml").getroot()
        root.find("compiler").set("meshdir", str((Path(robot_dir) / "assets").resolve()))
        articulate_mouth(root)
        robot = mujoco.MjSpec.from_string(ET.tostring(root, encoding="unicode"))
        spec.attach(robot, prefix=member + "_", frame=spec.worldbody.add_frame())
    model = spec.compile()
    # Give each attached duck a saturated, stable identity color without touching meshes.
    for geom_id in range(model.ngeom):
        body_name = model.body(model.geom_bodyid[geom_id]).name
        member = next((c for c in MEMBERS if body_name.startswith(c + "_")), None)
        if member is None:
            continue
        material = int(model.geom_matid[geom_id])
        if material >= 0:
            model.mat_rgba[material] = DUCK_RGBA[member]
        else:
            model.geom_rgba[geom_id] = DUCK_RGBA[member]
    model.opt.timestep = 0.005
    return model


class TurntableGame:
    """Per-tick spin, reverse-walk and measured elimination/recovery state."""

    def __init__(self, backend):
        self.b = backend
        self.spinner = backend.model.actuator("spinner").id
        self.spin_q = backend.model.jnt_qposadr[backend.model.joint("spin").id]
        self.spin_v = backend.model.jnt_dofadr[backend.model.joint("spin").id]
        self.target = 0.0
        self.escape_mode = False
        self.eliminated = []
        self.out = [False] * 4
        self.recovery_started = [None] * 4
        self.recovery_announced = [False] * 4
        self.events = []
        self._event_id = 0
        self.remaining = 4

    def _narrate(self, text):
        self._event_id += 1
        self.events.append({"id": self._event_id, "text": text})
        self.events = self.events[-20:]

    def set_spin(self, action_name):
        self.target = SPIN_SPEEDS[action_name]
        return {
            "verified": True,
            "spin": action_name,
            "target_omega": self.target,
            "rim_speed_mps": round(self.target * DISK_R, 2),
        }

    def halt(self):
        self.target = 0.0
        self.b.data.ctrl[self.spinner] = 0.0
        return {"verified": True, "spin": "spin_stop", "target_omega": 0.0}

    def set_escape(self, enabled=None):
        self.escape_mode = not self.escape_mode if enabled is None else bool(enabled)
        for i, d in enumerate(self.b.drivers):
            if not self.out[i]:
                d.policy = "walk" if self.escape_mode else "sitstand"
                d.command[:] = 0
                d.posture_target = d.rest_posture = "stand"
        return {
            "verified": True,
            "escape_mode": self.escape_mode,
            "message": "逆盘倒走已开启" if self.escape_mode else "逆盘倒走已关闭",
        }

    def _recover(self, i, elapsed):
        d = self.b.drivers[i]
        upright = float(self.b.data.xmat[d.body, 8]) > 0.94
        if upright:
            if self.recovery_started[i] is None:
                self.recovery_started[i] = elapsed
            elif elapsed - self.recovery_started[i] >= 0.5 and not self.recovery_announced[i]:
                self.recovery_announced[i] = True
                self._narrate(f"{i + 1}号自己站起来了，掌声鼓励！")
        elif (
            self.recovery_started[i] is not None
            and elapsed - self.recovery_started[i] >= 16
            and not self.recovery_announced[i]
        ):
            self.recovery_announced[i] = True
            self._narrate(f"{i + 1}号躺平了")

    def tick(self):
        b = self.b
        b.data.ctrl[self.spinner] = self.target
        omega = float(b.data.qvel[self.spin_v])
        elapsed = float(b.data.time)
        for i, d in enumerate(b.drivers):
            if self.out[i]:
                self._recover(i, elapsed)
                continue
            if self.escape_mode:
                pos = d.pose(b.data)[0]
                radius = math.hypot(pos[0], pos[1])
                desired = math.hypot(*SPAWNS[i])
                radial_error = desired - radius
                d.policy = "walk"
                d.command[:3] = [
                    max(-0.3, min(0.3, radial_error * 1.5)),
                    0.0,
                    max(-1.0, min(1.0, -self.target)),
                ]
            pos = d.pose(b.data)[0]
            radius = math.hypot(pos[0], pos[1])
            if radius > DISK_R:
                self.out[i] = True
                d.command[:] = 0
                d.policy = "walk"
                self.recovery_started[i] = elapsed
                self.eliminated.append(
                    {
                        "member": MEMBERS[i],
                        "at_s": round(elapsed, 2),
                        "radial_m": round(radius, 6),
                        "omega": round(abs(omega), 2),
                    }
                )
                self._narrate(f"{i + 1}号被甩出转盘，开始自己爬起")
        self.remaining = sum(not value for value in self.out)
        if (
            self.remaining == 1
            and abs(omega) > 0.1
            and not any(e["text"].startswith("冠军") for e in self.events)
        ):
            winner = next(i for i, value in enumerate(self.out) if not value)
            self._narrate(f"冠军是{winner + 1}号！")

    def snapshot(self):
        omega = float(self.b.data.qvel[self.spin_v])
        ducks = []
        for i, d in enumerate(self.b.drivers):
            pos = d.pose(self.b.data)[0]
            ducks.append(
                {
                    "member": MEMBERS[i],
                    "number": i + 1,
                    "color": DUCK_COLORS[MEMBERS[i]],
                    "out": self.out[i],
                    "radius_m": round(math.hypot(pos[0], pos[1]), 3),
                    "upright": round(float(self.b.data.xmat[d.body, 8]), 2),
                    "policy": d.policy,
                }
            )
        return {
            "angle": round(float(self.b.data.qpos[self.spin_q]), 3),
            "omega": round(omega, 2),
            "target_omega": self.target,
            "rim_speed_mps": round(abs(omega) * DISK_R, 2),
            "eliminated": list(self.eliminated),
            "remaining": self.remaining,
            "ducks": ducks,
            "escape_mode": self.escape_mode,
            "events": list(self.events),
                "source": "real_velocity_actuator_measured_eliminations",

        }
