"""BAM actuator setup, adapted from Pollen's Apache-2.0 infer_policy.py.

Keep the upstream electrical/friction contract, accepting both MuJoCo 3.3's
scalar joint damping and later MjSpec's three-component damping API.
"""

import mujoco
import numpy as np


class SpecCompatibility:
    """Pad short geom sizes used by newer MjSpec convenience APIs."""

    def __init__(self, spec):
        self.spec = spec

    def __getattr__(self, name):
        return getattr(self.spec, name)

    def body(self, name):
        return BodyCompatibility(self.spec.body(name))


class BodyCompatibility:
    def __init__(self, body):
        self.body = body

    def __getattr__(self, name):
        return getattr(self.body, name)

    def add_geom(self, **kwargs):
        if "size" in kwargs:
            kwargs["size"] = list(kwargs["size"]) + [0] * (3 - len(kwargs["size"]))
        return self.body.add_geom(**kwargs)


def compile_bam(spec, motor, *, timestep=0.005, vin_min=6):
    from bam.mujoco import MujocoController

    limit = motor.actuator.vin * motor.kt.value / motor.R.value
    names = []
    for actuator in spec.actuators:
        target = actuator.target
        name = target.name if hasattr(target, "name") else str(target)
        if name.startswith("passive_"):
            continue
        actuator.set_to_motor()
        actuator.forcelimited = True
        actuator.forcerange = (-limit, limit)
        actuator.ctrllimited = False
        actuator.gear = [1, 0, 0, 0, 0, 0]
        names.append(actuator.name)
        joint = next(j for j in spec.joints if j.name == name)
        try:
            joint.damping = 0
        except TypeError:
            joint.damping = np.zeros((3, 1))
        joint.frictionloss = 0
        joint.solref_friction = (-5e4, -2e2)
        joint.solimp_friction = (0.99, 0.9999, 0.001, 0.5, 2)
    model = spec.compile()
    model.opt.timestep = timestep
    data = mujoco.MjData(model)
    controller = MujocoController(motor, names, model, data, vin_drop_gain=None, vin_min=vin_min)
    return model, data, controller, names
