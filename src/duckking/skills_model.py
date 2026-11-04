"""Official floor/roller models, with an explicitly experimental expressive jaw."""

import xml.etree.ElementTree as ET

import mujoco

from .grasp_model import articulate_mouth


def build_skills_model(robot_dir, rollers=False):
    filename = "robot_groundcontact_rollers.xml" if rollers else "robot_groundcontact.xml"
    root = ET.parse(robot_dir / filename).getroot()
    root.find("compiler").set("meshdir", str((robot_dir / "assets").resolve()))
    if not rollers:
        articulate_mouth(root)
    ET.SubElement(
        root.find("worldbody"),
        "geom",
        name="floor",
        type="plane",
        size="4 4 .1",
        rgba=".83 .87 .78 1",
    )
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
    model.opt.timestep = 0.005
    # Same bearing friction as upstream scripts/infer_policy.py. Wheels stay passive.
    for j in range(model.njnt):
        if (model.joint(j).name or "").startswith("passive_"):
            model.dof_frictionloss[model.jnt_dofadr[j]] = 0.003
    return model
