"""Official visual meshes and a kinematic rig; exporting never steps physics."""

import base64
from functools import lru_cache
from pathlib import Path

import mujoco


def geometry(model, ids):
    meshes, geoms = {}, []
    for i in ids:
        mid = int(model.geom_dataid[i])
        if int(model.geom_type[i]) == 7 and mid not in meshes:
            va, vn = model.mesh_vertadr[mid], model.mesh_vertnum[mid]
            fa, fn = model.mesh_faceadr[mid], model.mesh_facenum[mid]
            meshes[mid] = {
                "vertices": base64.b64encode(
                    model.mesh_vert[va : va + vn].astype("<f4").tobytes()
                ).decode("ascii"),
                "faces": base64.b64encode(
                    model.mesh_face[fa : fa + fn].astype("<u4").tobytes()
                ).decode("ascii"),
            }
        material = int(model.geom_matid[i])
        rgba = model.mat_rgba[material] if material >= 0 else model.geom_rgba[i]
        geoms.append(
            {
                "id": i,
                "type": int(model.geom_type[i]),
                "mesh": mid,
                "size": model.geom_size[i].tolist(),
                "rgba": rgba.tolist(),
                "body": int(model.geom_bodyid[i]),
                "position": model.geom_pos[i].tolist(),
                "quaternion": model.geom_quat[i].tolist(),
            }
        )
    return {
        "meshes": meshes,
        "geoms": geoms,
        "attribution": "Pollen Robotics · CC BY-NC-SA 4.0 models",
    }


@lru_cache(maxsize=2)
def official_preview(assets: Path):
    from .simulation import HOME, POLICY_JOINTS

    model = mujoco.MjModel.from_xml_path(
        str(assets / "microduck_rl/src/mjlab_microduck/robot/microduck/robot_groundcontact.xml")
    )
    homes = dict(zip(POLICY_JOINTS, HOME, strict=True))
    bodies = []
    for i in range(1, model.nbody):
        joints = []
        for j in range(model.body_jntadr[i], model.body_jntadr[i] + model.body_jntnum[i]):
            if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE:
                continue
            name = model.joint(j).name
            joints.append(
                {
                    "name": name,
                    "axis": model.jnt_axis[j].tolist(),
                    "position": model.jnt_pos[j].tolist(),
                    "home": float(homes.get(name, 0)),
                }
            )
        bodies.append(
            {
                "id": i,
                "parent": int(model.body_parentid[i]),
                "name": model.body(i).name,
                "position": model.body_pos[i].tolist(),
                "quaternion": model.body_quat[i].tolist(),
                "joints": joints,
            }
        )
    return {
        **geometry(model, [i for i in range(model.ngeom) if model.geom_group[i] == 2]),
        "bodies": bodies,
        "physics": False,
        "source": "official_microduck_visuals",
        "model_commit": "b02fdea4902c2b93b7d34a83a6f05da4ececb7d3",
    }
