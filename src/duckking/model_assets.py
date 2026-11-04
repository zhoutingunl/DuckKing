"""Official visual meshes and a kinematic rig; exporting never steps physics."""

import base64
import gzip
import hashlib
import json
import logging
import struct
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import mujoco
import numpy as np


@dataclass(frozen=True)
class VisualAsset:
    version: str
    compressed: bytes
    decoded_bytes: int

    def manifest(self):
        return {
            "format": "dkm1", "version": self.version,
            "encoded_bytes": len(self.compressed), "decoded_bytes": self.decoded_bytes,
            "source": "official_microduck_visuals", "physics": False,
        }


def pack_visual_model(model):
    """DKM1: uint32 JSON length, aligned JSON header, aligned typed mesh buffers.

    Positions remain exact float32 values. Indices narrow to uint16 only when
    every value fits; this changes storage, never topology or physical geometry.
    """
    payload, meshes, shared = bytearray(), {}, {}
    for key, mesh in model["meshes"].items():
        arrays = {}
        for name, dtype in (("vertices", "<f4"), ("faces", "<u4")):
            values = np.frombuffer(base64.b64decode(mesh[name]), dtype=dtype)
            if name == "faces" and values.size and values.max() < 65536:
                values = values.astype("<u2")
            data = values.tobytes()
            array_key = (values.dtype.str, data)
            if array_key not in shared:
                payload.extend(b"\0" * (-len(payload) % 4))
                shared[array_key] = {
                    "offset": len(payload), "count": values.size, "bytes": values.dtype.itemsize,
                }
                payload.extend(data)
            arrays[name] = shared[array_key]
        meshes[key] = arrays
    metadata = json.dumps({**model, "meshes": meshes}, separators=(",", ":")).encode()
    return (
        b"DKM1" + struct.pack("<I", len(metadata)) + metadata
        + b"\0" * (-len(metadata) % 4) + payload
    )


_asset_lock = threading.Lock()


@lru_cache(maxsize=2)
def _visual_asset(assets):
    started = time.perf_counter()
    raw = pack_visual_model(official_preview(assets))
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    asset = VisualAsset(hashlib.sha256(compressed).hexdigest(), compressed, len(raw))
    logging.getLogger("uvicorn.error").info(
        "official_model_asset_built prepare_ms=%.1f decoded_bytes=%d encoded_bytes=%d",
        (time.perf_counter() - started) * 1000, len(raw), len(compressed),
    )
    return asset


def visual_asset(assets):
    # lru_cache alone can run the expensive first build twice for two rooms.
    with _asset_lock:
        return _visual_asset(assets)


def geometry(model, ids):
    meshes, geoms = {}, []
    # Appearance metadata follows the robot subtree, never a material's colour.
    # Objects and scenery retain their own materials even when their colours match a duck.
    owners = {}
    roots = {"trunk_base": "a", **{f"{c}_trunk_base": c for c in "abcd"}}
    for body in range(1, model.nbody):
        owners[body] = roots.get(model.body(body).name, owners.get(int(model.body_parentid[body])))
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
        owner = owners.get(int(model.geom_bodyid[i]))
        part = model.mesh(mid).name if int(model.geom_type[i]) == 7 else ""
        if owner:
            part = part.removeprefix(owner + "_")
        geoms.append(
            {
                "id": i,
                "type": int(model.geom_type[i]),
                "mesh": mid,
                "size": model.geom_size[i].tolist(),
                "rgba": rgba.tolist(),
                "duck": owner,
                "part": part,
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
