"""Matching stilt morphology and fixed release stages; no scripted robot motion."""

import math
from types import SimpleNamespace

import mujoco

from .feature_source import source_symbols

HEIGHTS = (10, 15, 20, 25, 50, 100, 140, 200)


def stilt_spec(spec, source, height):
    if height not in HEIGHTS:
        raise ValueError("请选择已发布策略对应的高跷高度")
    helpers = source_symbols(
        source / "stilt_constants.py",
        {
            "MIN_STILT_HEIGHT_CM",
            "MAX_STILT_HEIGHT_CM",
            "DEFAULT_STILT_MASS_BASE_KG",
            "DEFAULT_STILT_MASS_PER_CM_KG",
            "validate_stilt_morphology",
            "stilt_profile_dimensions",
            "default_stilt_mass_kg",
            "_rounded_rectangle_ring",
            "stilt_mesh_data",
            "get_stilt_walk_spec",
        },
        {
            "math": math,
            "mujoco": mujoco,
            "MICRODUCK_WALK_ROBOT_CFG": SimpleNamespace(spec_fn=lambda: spec),
        },
    )
    spec = helpers["get_stilt_walk_spec"](height, 0.5)
    for geom in spec.geoms:
        if geom.name.endswith("_original_sole_disabled"):
            geom.contype = geom.conaffinity = 0
    return spec


def flip_stage(spec):
    spec.worldbody.add_geom(
        name="platform",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=[0.30, 0.40, 0.03],
        pos=[-0.3, 0, 1.21342],
        rgba=[0.55, 0.45, 0.35, 1],
        friction=[1, 0.005, 0.0001],
        condim=3,
        priority=1,
        solref=[0.01, 1],
        solimp=[0.95, 0.99, 0.001, 0.5, 2],
    )
    spec.worldbody.add_geom(
        name="mat",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=[0.95077, 0.3025, 0.22171],
        pos=[0.97077, 0, 0.22171],
        rgba=[0.06, 0.27, 0.63, 1],
        friction=[0.9, 0.005, 0.0001],
        condim=3,
        priority=1,
        solref=[0.03, 1],
        solimp=[0.9, 0.95, 0.01, 0.5, 2],
    )
    spec.worldbody.add_geom(
        name="platform_pillar",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=[0.25, 0.3, 0.6],
        pos=[-0.3, 0, 0.6],
        rgba=[0.45, 0.37, 0.3, 1],
        contype=0,
        conaffinity=0,
        group=2,
    )
