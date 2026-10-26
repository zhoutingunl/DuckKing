"""Interactive turntable scene: real motor spin, measured eliminations."""

import asyncio
import math
from pathlib import Path

import pytest

from duckking.motion import Action, MotionController
from duckking.simulation import MuJoCoBackend

ASSETS = Path(__file__).resolve().parents[1] / "external"


@pytest.fixture
def backend():
    b = MuJoCoBackend(ASSETS)
    b.load("turntable")

    async def fast_loop():
        while True:
            b.tick()
            await asyncio.sleep(0.001)

    b._loop = fast_loop
    return b


async def run(motion, name, **kwargs):
    action = Action(name=name, **kwargs)
    await motion.submit(action)
    return await motion.wait(action.request_id)


async def test_spin_is_real_and_eliminations_are_measured(backend):
    motion = MotionController(backend)
    assert (await run(motion, "spin_fast"))["outcome"]["target_omega"] == pytest.approx(4.0)
    deadline = backend.data.time + 40
    while backend.data.time < deadline and backend.turntable.snapshot()["remaining"] == 4:
        await asyncio.sleep(0.05)
    state = backend.turntable.snapshot()
    assert state["remaining"] < 4, "高速转盘必须产生真实出局"
    assert state["eliminated"], "出局必须带测量记录"
    for entry in state["eliminated"]:
        assert entry["radial_m"] > 1.02  # measured rim crossing, not a timer
    assert abs(state["omega"]) > 1.0  # the disk really spins
    assert state["source"] == "real_velocity_actuator_measured_eliminations"
    assert (await run(motion, "spin_stop"))["outcome"]["target_omega"] == 0.0
    await asyncio.sleep(1.0)
    assert abs(backend.turntable.snapshot()["omega"]) < 1.0  # motor actually brakes


async def test_sit_and_stand_work_on_the_disk_surface(backend):
    motion = MotionController(backend)
    seated = await run(motion, "sit", target="c")  # any member, not just duck A
    assert seated["status"] == "completed"  # posture windows use the disk offset
    standing = await run(motion, "stand", target="c")
    assert standing["status"] == "completed"


async def test_scene_gates_and_switch(backend):
    motion = MotionController(backend)
    denied = await run(motion, "walk")
    assert denied["status"] == "failed" and "转速" in denied["error"]
    switched = await run(motion, "scene_ball")
    assert switched["status"] == "completed"
    assert backend.scene == "ball"
    assert backend.turntable is None
    back = await run(motion, "scene_turntable")
    assert back["status"] == "completed"
    state = backend.turntable.snapshot()
    assert state["remaining"] == 4 and not state["eliminated"]


async def test_eliminated_ducks_can_self_recover_on_the_floor(backend):
    motion = MotionController(backend)
    await run(motion, "spin_fast")
    deadline = backend.data.time + 40
    while backend.data.time < deadline and not backend.turntable.eliminated:
        await asyncio.sleep(0.05)
    assert backend.turntable.eliminated
    await run(motion, "spin_stop")
    index = "abcd".index(backend.turntable.eliminated[0]["member"])
    driver = backend.drivers[index]
    driver.command[:] = 0
    driver.policy = "walk"
    stable, _took = None, 0.0
    while _took < 14.0:
        upright = float(backend.data.xmat[driver.body, 8])
        stable = backend.data.time if upright > 0.94 and stable is None else (
            stable if upright > 0.94 else None)
        if stable is not None and backend.data.time - stable >= 0.5:
            break
        await asyncio.sleep(0.02)
        _took += 0.02
    assert stable is not None, "被甩出的鸭必须能自己站起来"
