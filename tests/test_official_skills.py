"""Actual MuJoCo outcomes and cancellation; accelerated physics is explicitly labelled."""

import asyncio
import json
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from duckking.mcp import DeviceMCP
from duckking.motion import Action, MotionController, PreviewBackend
from duckking.motion_catalog import SKILL_DURATIONS
from duckking.simulation import MuJoCoBackend

ASSETS = Path(__file__).resolve().parents[1] / "external"


@pytest.fixture
def backend():
    b = MuJoCoBackend(ASSETS)

    async def fast_loop():
        # Keep the same 200 Hz integration and 50 Hz inference. Only wall-clock pacing changes.
        while True:
            for _ in range(4):
                b.tick()
            await asyncio.sleep(0.001)

    b._loop = fast_loop
    return b


async def run(motion, name, **kwargs):
    action = Action(name=name, **kwargs)
    await motion.submit(action)
    return await motion.wait(action.request_id)


@pytest.mark.parametrize(
    "scene,name",
    [
        ("skills", "roulade"),
        ("skills", "ground_pick"),
        ("skills", "yawn"),
        ("rollers", "skate"),
        ("rollers", "roller_crouch"),
    ],
)
async def test_actual_new_motion_and_return_to_supported_stance(backend, scene, name):
    backend.load(scene)
    motion = MotionController(backend)
    try:
        # Test after full settling too; a launch immediately after reset can hide dead zones.
        for _ in range(150):
            backend.tick()
        result = await run(motion, name)
        assert result["status"] == "completed", result
        out = result["outcome"]
        assert out["verified"] and out["supported"] and out["stable_s"] >= 0.3
        assert not out["object_grasped"]
        if name == "roulade":
            assert out["min_upright"] < -0.5 and out["rotation_rad"] > 5
        elif name == "ground_pick":
            assert 0 < out["min_mouth_height_m"] < 0.04
        elif name == "yawn":
            assert out["max_mouth_open_rad"] > 0.20
            assert out["source"] == "local_choreography"
        elif name == "skate":
            assert out["displacement_m"] > 0.05 and out["wheel_rotation_rad"] > 1
            assert len(backend.skill_run.wheels) == 4
        else:
            assert out["min_body_height_m"] < 0.09
        assert not backend.drivers[0].command.any()
        assert backend.drivers[0].policy == backend.drivers[0].base_policy
    finally:
        await motion.close()


@pytest.mark.parametrize(
    "scene,name",
    [
        ("skills", "roulade"),
        ("skills", "ground_pick"),
        ("skills", "yawn"),
        ("rollers", "skate"),
        ("rollers", "roller_crouch"),
    ],
)
async def test_stop_cancels_policy_and_no_late_phase_or_mouth_command(backend, scene, name):
    backend.load(scene)
    motion = MotionController(backend)
    try:
        action = Action(name=name)
        await motion.submit(action)
        for _ in range(100):
            if backend.skill_run and backend.data.time > backend.skill_run.start + 0.24:
                break
            await asyncio.sleep(0.001)
        assert backend.skill_run and backend.skill_run.status == "running"
        assert (await run(motion, "stop"))["status"] == "completed"
        assert (await motion.wait(action.request_id))["status"] == "cancelled"
        assert backend.skill_run.status == "interrupted"
        await asyncio.sleep(0.03)
        assert not backend.drivers[0].command.any()
        assert backend.drivers[0].policy == backend.drivers[0].base_policy
        if backend.idle:
            assert backend.data.ctrl[backend.idle.mouth] == 0
    finally:
        await motion.close()


async def test_idle_yawn_yields_to_commands_and_explicit_stop_disables_it(backend):
    backend.load("skills")
    motion = MotionController(backend)
    try:
        assert (await run(motion, "idle_on"))["outcome"]["idle_enabled"]
        start = backend.data.time
        saw_glance = saw_yawn = False
        while backend.data.time - start < 18:
            saw_glance |= backend.idle.phase == "look_around"
            saw_yawn |= backend.idle.phase == "yawn"
            await asyncio.sleep(0.001)
        assert saw_glance and saw_yawn
        action = Action(name="shake_head", duration=0.2)
        await motion.submit(action)
        await asyncio.sleep(0.01)
        assert backend.idle.phase == "paused"
        await motion.wait(action.request_id)
        await run(motion, "stop")
        assert not backend.idle.enabled
        await asyncio.sleep(0.05)
        assert not backend.drivers[0].command.any()
        assert backend.data.ctrl[backend.idle.mouth] == 0
        await run(motion, "idle_on")
        await run(motion, "idle_off")
        assert not backend.idle.enabled
        await run(motion, "idle_on")
        await run(motion, "scene_ball")
        assert backend.idle is None
    finally:
        await motion.close()


async def test_no_motion_is_not_verified_just_because_time_elapsed(backend, monkeypatch):
    backend.load("skills")

    def frozen_pose():
        backend.data.time += 0.02
        if backend.skill_run:
            backend.skill_run.tick()

    monkeypatch.setattr(backend, "tick", frozen_pose)
    motion = MotionController(backend)
    try:
        for name in ("roulade", "ground_pick", "yawn"):
            result = await run(motion, name)
            assert result["status"] == "failed" and not result["outcome"]["verified"]
            assert not backend.drivers[0].command.any()
    finally:
        await motion.close()


async def test_scene_guards_bounds_and_mcp_failure_results(backend):
    motion = MotionController(backend)
    mcp = DeviceMCP(motion, "skills-test")
    try:
        listing = await mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert {"duck_roulade", "duck_ground_pick", "duck_skate", "duck_yawn"} <= {
            t["name"] for t in listing["result"]["tools"]
        }
        call = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "duck_roulade", "arguments": {}},
        }
        response = await mcp.handle(call)
        assert response["result"]["isError"]
        assert json.loads(response["result"]["content"][0]["text"])["status"] == "failed"
        await run(motion, "scene_skills")
        call["id"] = 3
        response = await mcp.handle(call)
        assert not response["result"]["isError"], response
        await run(motion, "scene_rollers")
        for name in ("roulade", "ground_pick", "walk", "strafe_left", "sit", "idle_on"):
            assert (await run(motion, name))["status"] == "failed"
        for name, duration in SKILL_DURATIONS.items():
            for kwargs in ({"duration": duration + 0.1}, {"speed": 0.3}):
                with pytest.raises(ValidationError):
                    Action(name=name, **kwargs)
    finally:
        await mcp.close()
        await motion.close()
    preview = MotionController(PreviewBackend())
    try:
        for name in SKILL_DURATIONS:
            assert (await run(preview, name))["status"] == "failed"
    finally:
        await preview.close()


@pytest.mark.parametrize(
    "name,axis,sign",
    [
        ("backward", 0, -1),
        ("strafe_left", 1, 1),
        ("strafe_right", 1, -1),
    ],
)
async def test_actual_backward_and_lateral_direction(backend, name, axis, sign):
    # These use wall-clock bounded MotionController, so restore normal pacing.
    backend._loop = MuJoCoBackend._loop.__get__(backend)
    motion = MotionController(backend)
    start = backend.drivers[0].pose(backend.data)[0]
    try:
        assert (await run(motion, name, duration=1.2))["status"] == "completed"
        end = backend.drivers[0].pose(backend.data)[0]
        assert (end[axis] - start[axis]) * sign > 0.02
        assert backend.data.xmat[backend.drivers[0].body, 8] > 0.9
        assert np.all(backend.drivers[0].command == 0)
    finally:
        await motion.close()
