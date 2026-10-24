"""Experimental articulated beak derived from the pinned official mesh model.

The upstream RL model fuses the mouth. We split its lower jaw visuals into a
hinge and add two explicit contact pads; this is NOT an official calibrated
mouth mechanism. Object motion is exclusively MuJoCo contact + gravity.
"""

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco

MOUTH_OPEN = math.radians(30)
MOUTH_CLOSED = math.radians(-5)
PAD_UPPER = (-0.006, 0, -0.063)
PAD_LOWER = (-0.014, 0, -0.063)
PIVOT = (0.003, 0, -0.018)


def numbers(values):
    return " ".join(str(float(v)) for v in values)


def build_grasp_model(robot_dir: Path):
    tree = ET.parse(robot_dir / "robot_groundcontact.xml")
    root = tree.getroot()
    root.find("compiler").set("meshdir", str((robot_dir / "assets").resolve()))
    head = root.find('.//body[@name="jaw_soft"]')
    lower = ET.SubElement(head, "body", name="grasp_jaw", pos=numbers(PIVOT))
    ET.SubElement(
        lower,
        "joint",
        name="mouth",
        type="hinge",
        axis="0 1 0",
        range=numbers((MOUTH_CLOSED, MOUTH_OPEN)),
        damping="0.015",
        frictionloss="0.001",
        armature="0.00002",
    )
    # Keep total head mass unchanged. The split inertia is an approximation.
    inertial = head.find("inertial")
    mass = float(inertial.get("mass"))
    inertial.set("mass", str(mass - 0.012))
    inertial.set(
        "fullinertia",
        numbers(float(x) * (mass - 0.012) / mass for x in inertial.get("fullinertia").split()),
    )
    ET.SubElement(
        lower,
        "inertial",
        pos="-0.012 0 -0.035",
        mass="0.012",
        diaginertia="0.000012 0.000009 0.000014",
    )
    for geom in list(head.findall("geom")):
        if geom.get("mesh") in {"jaw", "jaw_soft", "bottom_head_shell"}:
            pos = [float(x) for x in geom.get("pos", "0 0 0").split()]
            geom.set("pos", numbers(p - v for p, v in zip(pos, PIVOT, strict=True)))
            head.remove(geom)
            lower.append(geom)
    for parent, name, position in [
        (head, "upper_pad", PAD_UPPER),
        (lower, "lower_pad", tuple(p - v for p, v in zip(PAD_LOWER, PIVOT, strict=True))),
    ]:
        ET.SubElement(
            parent,
            "geom",
            name=name,
            type="box",
            pos=numbers(position),
            size="0.0015 0.018 0.016" if name == "upper_pad" else "0.0015 0.018 0.006",
            rgba="0.9 0.45 0.12 1",
            group="2",
            contype="4",
            conaffinity="4",
            friction="1.3 0.01 0.001",
            condim="4",
            solref="0.02 1",
            solimp="0.95 0.99 0.001",
            mass="0",
        )
    ET.SubElement(
        root.find("actuator"),
        "position",
        name="mouth",
        joint="mouth",
        kp="0.3",
        kv="0.008",
        ctrlrange=numbers((MOUTH_CLOSED, MOUTH_OPEN)),
        forcerange="-0.025 0.025",
    )
    world = root.find("worldbody")
    ET.SubElement(
        world,
        "geom",
        name="floor",
        type="plane",
        size="4 4 .1",
        rgba=".83 .87 .78 1",
        contype="5",
        conaffinity="5",
    )
    obj = ET.SubElement(world, "body", name="carry_object", pos=".062 -.002 .208")
    ET.SubElement(obj, "freejoint", name="object_free")
    ET.SubElement(
        obj,
        "geom",
        name="object_geom",
        type="box",
        size=".010 .065 .004",
        mass=".004",
        group="2",
        rgba=".23 .52 .81 1",
        contype="4",
        conaffinity="4",
        friction="1.3 0.01 .001",
        condim="4",
        solref=".02 1",
    )
    stand = ET.SubElement(world, "body", name="source_stand", pos=".062 -.002 0")
    for side in (-1, 1):
        ET.SubElement(
            stand,
            "geom",
            name=f"source_support_{side}",
            type="box",
            pos=numbers((0, side * 0.077, 0.202)),
            size=".010 .023 .002",
            rgba=".68 .73 .61 1",
            group="2",
            contype="5",
            conaffinity="5",
            friction="1 .01 .001",
        )
        ET.SubElement(
            stand,
            "geom",
            name=f"source_post_{side}",
            type="box",
            pos=numbers((0, side * 0.096, 0.1)),
            size=".010 .004 .1",
            rgba=".68 .73 .61 1",
            group="2",
            contype="5",
            conaffinity="5",
        )
    tray = ET.SubElement(world, "body", name="destination_stand", pos=".30 0 0")
    ET.SubElement(
        tray,
        "geom",
        name="destination_support",
        type="box",
        pos="0 0 .172",
        size=".075 .14 .004",
        rgba=".79 .69 .30 1",
        group="2",
        contype="5",
        conaffinity="5",
        friction="1 .01 .001",
    )
    for side in (-1, 1):
        ET.SubElement(
            tray,
            "geom",
            name=f"destination_post_{side}",
            type="box",
            pos=numbers((0.055, side * 0.13, 0.084)),
            size=".008 .008 .084",
            rgba=".65 .57 .28 1",
            group="2",
            contype="5",
            conaffinity="5",
        )
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
    model.opt.timestep = 0.005
    model.opt.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    model.opt.iterations = 80
    return model
