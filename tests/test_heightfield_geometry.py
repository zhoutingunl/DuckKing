import base64

import mujoco
import numpy as np
import pytest

from duckking.model_assets import geometry


def test_exported_heightfield_surface_matches_mujoco_ray_not_flat_plane():
    spec = mujoco.MjSpec.from_string("""<mujoco><asset>
      <hfield name="terrain" nrow="2" ncol="2" size="1 1 1 .1" elevation="0 0 0 1"/>
      </asset><worldbody><geom name="terrain" type="hfield" hfield="terrain"
      pos=".2 -.3 .4" euler="0 0 31"/></worldbody></mujoco>""")
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    exported = geometry(model, [0])
    assert exported["geoms"][0]["type"] == 7
    mesh = exported["meshes"][exported["geoms"][0]["mesh"]]
    vertices = np.frombuffer(base64.b64decode(mesh["vertices"]), "<f4").reshape(-1, 3)
    triangles = np.frombuffer(base64.b64decode(mesh["faces"]), "<u4").reshape(-1, 3)
    assert np.ptp(vertices[:, 2]) == pytest.approx(1)
    rotation = data.geom_xmat[0].reshape(3, 3)
    heights = []
    for x, y in ((-0.5, -0.3), (0.5, -0.5), (0.1, 0.7), (0.8, 0.2), (-0.7, -0.8)):
        for triangle in triangles:
            points = vertices[triangle]
            weights = np.linalg.solve(np.vstack([points[:, :2].T, np.ones(3)]), [x, y, 1])
            if weights.min() >= -1e-6:
                expected = float(weights @ points[:, 2]) + 0.4
                break
        else:
            pytest.fail("mesh has a missing triangle")
        origin = rotation @ [x, y, 2] + data.geom_xpos[0]
        hit = np.array([-1], np.int32)
        distance = mujoco.mj_ray(
            model, data, origin, np.array([0.0, 0.0, -1.0]), None, True, -1, hit
        )
        assert hit[0] == 0
        assert origin[2] - distance == pytest.approx(expected, abs=1e-6)
        heights.append(expected)
    assert max(heights) > min(heights) + 0.2
