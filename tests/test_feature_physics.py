"""Pinned CPU policies exercised against actual MuJoCo contacts and camera pixels.

CI installs the optional assets. A minimal checkout may skip this module, but
cannot use that skip as evidence that a policy passes physical acceptance.
"""
import asyncio
import gc
import os
import sys
from pathlib import Path

import pytest

ASSETS = Path(__file__).resolve().parents[1] / "external"
pytestmark = pytest.mark.skipif(
    not (ASSETS / "features/policies/hop/policy.onnx").is_file(),
    reason="optional functional-scene assets are not installed",
)


@pytest.fixture
def runtime(monkeypatch):
    environment = {
        key: os.environ.get(key)
        for key in ("MICRODUCK_RL_DIR", "MICRODUCK_POLICY_DIR", "MICRODUCK_ROOT")
    }
    monkeypatch.syspath_prepend(str(ASSETS / "features/python"))
    monkeypatch.syspath_prepend(str(ASSETS / "features/bam"))
    if sys.platform.startswith("linux"):
        monkeypatch.setenv("MUJOCO_GL", "osmesa")
    original_sleep = asyncio.sleep

    async def fast_sleep(delay):
        # Remove only presentation pacing: every MuJoCo step and contact sample
        # is retained, with a scheduler yield for cancellation/worker callbacks.
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    try:
        yield original_sleep
    finally:
        for key, value in environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # Native mesh/renderer allocations are much larger than the Python
        # objects that own them, so Python's allocation counter is a poor trigger.
        gc.collect()


@pytest.mark.parametrize(
    ("capability", "actions"),
    [
        ("emotions", ("curious", "devastated", "yes", "sad", "mmh", "yes_fast", "no",
                      "defiant", "angry", "mock", "excited", "impatient", "laugh")),
        ("dock", ("dock", "undock")),
        ("hop", ("hop",)),
        ("flamingo", ("lift_left", "lift_right", "lower")),
        ("step", ("cross",)),
        ("senses", ("observe", "look_left", "look_forward", "look_right")),
        ("theremin", ("near", "play", "far")),
        ("search", ("find_red", "find_blue", "find_green")),
        ("soccer", ("kick_left", "kick_right")),
        ("navigation", ("go_door", "go_home", "go_table")),
        ("footsteps", ("steps",)),
        ("swing", ("swing",)),
    ],
)
async def test_pinned_policy_physical_acceptance(runtime, capability, actions):
    import numpy as np

    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, capability)
    try:
        assert len(world.geometry()["geoms"]) > 60
        for index, action in enumerate(actions):
            if index and capability not in {"dock", "emotions", "theremin", "senses"}:
                await world.reset()
            world.metrics = {}  # Same command boundary as the real worker.
            outcome = await world.perform(FeatureCommand(action=action))
            state = await world.snapshot()
            assert np.isfinite(world.data.qpos).all()
            assert state["geoms"] and state["ducks"]
            if capability == "swing":
                assert outcome["swing_span_deg"] > 20
                assert outcome["verified"] == outcome["geometry_valid"]
                assert len(state["geoms"]) == len(world.geometry()["geoms"])
            else:
                assert outcome["verified"], (capability, action, outcome)
            if capability in {"search", "soccer", "senses", "theremin"}:
                assert state["sensors"]["image"]  # actual rendered RGB, not a mock
            if capability == "dock":
                assert outcome["virtual_battery_percent"] == pytest.approx(22)
                assert outcome["charging_proxy"] == (action == "dock")
            await world.stop()
    finally:
        await world.close()


async def test_circus_cancel_releases_thread_and_reset_does_not_start(runtime):
    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, "circus")
    try:
        state = await world.snapshot()
        assert len(state["ducks"]) == 3
        assert not world.begin.is_set()
        task = asyncio.create_task(world.perform(FeatureCommand(action="jump_rope")))
        async with asyncio.timeout(60):
            while world.metrics.get("sim_time", 0) <= 2:
                await runtime(0.05)
        assert world.metrics["sim_time"] > 2
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await world.stop()
        assert not world.thread.is_alive()
        await world.reset()
        assert not world.begin.is_set()
        assert (await world.snapshot())["sim_time"] < 2
    finally:
        await world.close()


@pytest.mark.parametrize(("capability", "action"), [("hop", "hop"), ("movement", "walk")])
async def test_real_worker_cancel_reset_and_release_are_acknowledged(capability, action):
    from duckking.feature_backend import FeatureBackend

    backend = await FeatureBackend.create(ASSETS, capability)
    try:
        assert backend.geometry()["physics"]
        assert (await backend.snapshot())["feature"]["status"] == "idle"
        initial_time = (await backend.snapshot())["sim_time"]
        await asyncio.sleep(.6)
        assert (await backend.snapshot())["sim_time"] == initial_time
        first = await backend.invoke({"action": action, "request_id": "physical-action"})
        assert first["status"] == "running"
        assert (await backend.snapshot())["feature"]["status"] == "running"
        await asyncio.sleep(.2)
        await backend.stop()
        stopped_time = (await backend.snapshot())["sim_time"]
        await asyncio.sleep(.6)
        assert (await backend.snapshot())["sim_time"] == stopped_time
        await backend.reset()
        for _ in range(100):
            if (await backend.snapshot())["feature"]["status"] == "idle":
                break
            await asyncio.sleep(.05)
        else:
            pytest.fail("reset did not publish idle state")
        assert not backend.error
    finally:
        await backend.close()
    assert backend.process.returncode is not None
    with pytest.raises(ValueError, match="释放"):
        await backend.invoke({"action": action})
