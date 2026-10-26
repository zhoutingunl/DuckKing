"""Real 200 Hz physics; accelerated wall pacing is only used by these tests."""

import asyncio
import math
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from duckking.mcp import DeviceMCP
from duckking.motion import Action, MotionController, PreviewBackend
from duckking.simulation import MuJoCoBackend
from duckking.stage import MEMBERS, SLOTS, StageSelection, path_to, scatter


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.setattr("duckking.simulation.secrets.randbelow", lambda _: 3)
    b = MuJoCoBackend(Path(__file__).resolve().parents[1] / "external")
    b.load("stage")

    async def fast_loop():
        while True:
            b.tick()
            await asyncio.sleep(0.001)

    b._loop = fast_loop
    return b


async def run(motion, name, **kwargs):
    a = Action(name=name, **kwargs)
    await motion.submit(a)
    return await motion.wait(a.request_id)


@pytest.mark.parametrize("seed", [1, 2, 3, 7, 10])
async def test_random_scatter_gathers_with_real_motion_then_rolls_and_dances(
    backend, monkeypatch, seed
):
    monkeypatch.setattr("duckking.simulation.secrets.randbelow", lambda _: seed)
    backend.load("stage")
    initial = backend.stage.positions()
    motion = MotionController(backend)
    try:
        result = await run(motion, "stage_gather")
        assert result["status"] == "completed", result
        out = result["outcome"]
        assert out["arrived"] == [True] * 4 and not out["running"]
        assert all(out["yawns"])
        assert (
            max(math.dist(p, q) for p, q in zip(initial, backend.stage.positions(), strict=True))
            > 0.15
        )
        assert all(
            math.dist(p, q) < 0.18 for p, q in zip(backend.stage.positions(), SLOTS, strict=True)
        )
        waiting = backend.stage.positions()
        backend.stage.select(
            StageSelection(
                target="c",
                order=list("dcba"),
                revision=backend.revision,
                instance=backend.stage.instance,
            )
        )
        result = await run(motion, "stage_roll", member="selected")
        assert result["status"] == "completed", result
        assert result["outcome"]["member"] == "c"
        assert result["outcome"]["rotation_rad"] > 5 and result["outcome"]["returned"]
        assert all(
            math.dist(p, waiting[i]) < 0.12
            for i, p in enumerate(backend.stage.positions())
            if i != 2
        )
        result = await run(motion, "stage_dance")
        assert result["status"] == "completed", result
        assert result["outcome"]["clock"] == "shared_mujoco_sim_time"
        assert result["outcome"]["members"] == list(MEMBERS)
        assert len(result["outcome"]["phases"]) == 7
        assert all(not d.command.any() for d in backend.drivers)
    finally:
        await motion.close()


async def test_cancel_and_replace_clear_all_four_commands_mouths_and_forces(backend):
    motion = MotionController(backend)
    try:
        for replacement in ("stop", "scene_duo"):
            backend.load("stage")
            a = Action(name="stage_gather")
            await motion.submit(a)
            await asyncio.sleep(0.1)
            assert (await run(motion, replacement))["status"] == "completed"
            assert (await motion.wait(a.request_id))["status"] == "cancelled"
            assert all(not d.command.any() for d in backend.drivers)
            assert not backend.data.xfrc_applied.any()
            if replacement == "stop":
                assert not backend.stage.running and backend.stage.phase == "stopped"
                assert not backend.data.ctrl[backend.stage.mouths].any()
    finally:
        await motion.close()


async def test_poke_targets_selected_body_is_bounded_and_always_releases_force(backend):
    motion = MotionController(backend)
    try:
        initial = backend.stage.positions()
        result = await run(motion, "stage_poke", member="d")
        assert result["status"] == "completed", result
        assert result["outcome"]["member"] == "d"
        assert result["outcome"]["force_n"] == 1
        assert math.dist(initial[3], backend.stage.positions()[3]) > 0.0001
        assert not backend.data.xfrc_applied.any()
        a = Action(name="stage_poke", member="b")
        await motion.submit(a)
        await asyncio.sleep(0.002)
        await run(motion, "stop")
        assert (await motion.wait(a.request_id))["status"] in {"cancelled", "completed"}
        assert not backend.data.xfrc_applied.any()
    finally:
        await motion.close()


async def test_stage_failure_is_explicit_and_never_uses_preview(backend, monkeypatch):
    motion = MotionController(backend)
    try:
        assert (await run(motion, "stage_roll"))["status"] == "failed"
        assert (await run(motion, "stage_dance"))["status"] == "failed"
        assert (await run(motion, "walk"))["status"] == "failed"
        monkeypatch.setattr(
            backend.stage, "guard", lambda: (_ for _ in ()).throw(ValueError("solver"))
        )
        result = await run(motion, "stage_gather")
        assert result["status"] == "failed" and result["error"] == "solver"
        assert not backend.stage.running
        assert all(not d.command.any() for d in backend.drivers)
        backend.load("ball")
        assert (await run(motion, "stage_gather"))["status"] == "failed"
    finally:
        await motion.close()
    preview = MotionController(PreviewBackend())
    try:
        assert (await run(preview, "stage_gather"))["status"] == "failed"
    finally:
        await preview.close()


async def test_stage_mcp_lists_only_stage_tools_and_honors_screen_identity(backend):
    motion = MotionController(backend)
    mcp = DeviceMCP(motion, "stage-test")
    try:
        result = await mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert {t["name"] for t in result["result"]["tools"]} == {
            "duck_stop",
            "duck_get_status",
            "duck_stage_gather",
            "duck_stage_roll",
            "duck_stage_dance",
        }
        backend.stage.select(
            StageSelection(
                target="b",
                order=list("dcba"),
                revision=backend.revision,
                instance=backend.stage.instance,
            )
        )
        assert backend.stage.member("selected") == "b" and backend.stage.member("leftmost") == "d"
        bad = await mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "duck_stage_roll", "arguments": {"member": "all"}},
            }
        )
        assert bad["result"]["isError"]
    finally:
        await motion.close()


def test_random_layout_and_planner_are_bounded_reproducible_and_avoid_other_ducks():
    for seed in range(50):
        poses = scatter(seed)
        assert poses == scatter(seed)
        assert all(-1.1 < x < 1.1 and -1.1 < y < 1.1 for x, y, _ in poses)
        assert all(
            math.dist(a[:2], b[:2]) > 0.38 for i, a in enumerate(poses) for b in poses[i + 1 :]
        )
    path = path_to((-0.6, 0), (0.6, 0), [(0, 0)])
    assert path and all(math.dist(p, (0, 0)) >= 0.25 for p in path)
    assert not path_to((0, 0), (5, 5), [])
    for values in (
        {"duration": 999},
        {"duration": 1},
        {"speed": 0.2},
        {"member": "all"},
        {"target": "b"},
    ):
        with pytest.raises(ValidationError):
            Action(name="stage_roll", **values)
    with pytest.raises(ValidationError):
        StageSelection(target="a", order=list("aabc"), revision="old", instance="old")
    np.testing.assert_equal(len(SLOTS), 4)


async def test_actual_duck_contact_triggers_one_measured_sit_stand_and_resumes(backend):
    import mujoco

    # Explicit test initial conditions create real contact, never mock its event.
    for d, (x, y) in zip(
        backend.drivers, [(0, -0.065), (0, 0.065), (-0.6, 0.65), (0.6, 0.85)], strict=True
    ):
        backend.data.qpos[d.root : d.root + 7] = [x, y, 0.125, 1, 0, 0, 0]
    mujoco.mj_forward(backend.model, backend.data)
    motion = MotionController(backend)
    try:
        result = await run(motion, "stage_gather")
        assert result["status"] == "completed", result
        reactions = result["outcome"]["reactions"]
        assert len(reactions) == 1 and reactions[0]["pair"] == ["a", "b"]
        assert reactions[0]["member"] in {"a", "b"}
        assert reactions[0]["sit"]["verified"] and reactions[0]["stand"]["verified"]
        assert reactions[0]["sit"]["ducks"][0]["observed"] == "sit"
        assert result["outcome"]["arrived"] == [True] * 4
    finally:
        await motion.close()


async def test_reference_is_captured_per_voice_turn_and_stale_selection_is_rejected(backend):
    backend.stage.select(
        StageSelection(
            target="c",
            order=list("dcba"),
            revision=backend.revision,
            instance=backend.stage.instance,
        )
    )
    backend.stage.capture_reference()
    backend.stage.select(
        StageSelection(
            target="b",
            order=list("abcd"),
            revision=backend.revision,
            instance=backend.stage.instance,
        )
    )
    assert backend.stage.voice_reference == (("c",), "d")
    with pytest.raises(ValueError, match="重置"):
        backend.stage.select(
            StageSelection(target="a", revision="stale", instance=backend.stage.instance)
        )


def test_selection_endpoint_validates_room_revision_and_order(tmp_path):
    from fastapi.testclient import TestClient

    from duckking.app import create_app
    from duckking.config import Settings

    app = create_app(settings=Settings(data_dir=tmp_path, secrets_file=tmp_path / "none"))
    with TestClient(app) as client:
        start = client.post("/api/scenes/start", json={"name": "scene_stage"})
        assert start.status_code == 202
        import time

        for _ in range(200):
            state = client.get("/api/scenes/state").json()
            if state["backend"]["scene"] == "stage":
                break
            time.sleep(0.01)
        revision = state["backend"]["revision"]
        valid = {
            "target": "d",
            "order": list("dcba"),
            "revision": revision,
            "instance": state["backend"]["stage"]["instance"],
        }
        assert client.post("/api/scenes/stage/selection", json=valid).json()["selected"] == ["d"]
        assert (
            client.post(
                "/api/scenes/stage/selection", json=valid | {"order": list("aaaa")}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/scenes/stage/selection", json=valid | {"revision": "stale"}
            ).status_code
            == 422
        )


async def test_voice_reference_is_used_by_mcp_even_if_selection_changes(backend, monkeypatch):
    motion = MotionController(backend)
    mcp = DeviceMCP(motion, "reference")
    backend.stage.selected = ["b", "c"]
    backend.stage.order = list("dcba")
    backend.stage.capture_reference()
    backend.stage.selected = ["a"]
    backend.stage.order = list("abcd")
    seen = []

    async def submit(action):
        seen.append(action)

    async def wait(_request_id):
        return {"status": "completed"}

    monkeypatch.setattr(motion, "submit", submit)
    monkeypatch.setattr(motion, "wait", wait)
    for i, member in enumerate(["selected", "leftmost", "b"]):
        result = await mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": i,
                "method": "tools/call",
                "params": {"name": "duck_stage_roll", "arguments": {"member": member}},
            }
        )
        assert not result["result"]["isError"]
    assert seen[0].members == ["b", "c"]
    assert [a.member for a in seen[1:]] == ["d", "b"]
    result = await mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "duck_set_scene", "arguments": {"scene": "skills"}},
        }
    )
    assert result["result"]["isError"] and len(seen) == 3
    await motion.close()


async def test_slow_but_advancing_stage_does_not_hit_response_idle_and_still_has_turn_cap(
    backend,
    tmp_path,
    monkeypatch,
):
    import time

    from duckking.config import Settings
    from duckking.diagnostics import VoiceDiagnostics
    from duckking.voice import VoiceSession

    async def send(_data):
        pass

    motion = MotionController(backend)
    session = VoiceSession(
        send, motion, Settings(data_dir=tmp_path), VoiceDiagnostics(tmp_path / "voice.jsonl")
    )
    monkeypatch.setattr("duckking.voice.WATCHDOG_INTERVAL", 0.01)
    monkeypatch.setattr("duckking.voice.RESPONSE_TIMEOUT", 0.04)
    monkeypatch.setattr("duckking.voice.TURN_TIMEOUT", 0.20)
    resets = []

    async def reset():
        resets.append(True)

    monkeypatch.setattr(session, "reset", reset)
    backend.stage.running = True
    motion.current = {"id": "bounded-stage"}
    session.state = "thinking"
    session.started = session.last_activity = time.monotonic()
    watcher = asyncio.create_task(session._watch())
    for _ in range(10):
        backend.data.time += 0.02
        await asyncio.sleep(0.01)
    assert not resets
    await asyncio.wait_for(watcher, 0.5)
    assert resets == [True]
    motion.current = None
    await motion.close()


def selection_for(backend, **changes):
    return StageSelection(revision=backend.revision, instance=backend.stage.instance, **changes)


async def test_multiselect_toggle_empty_and_roll_each_selected_robot(backend):
    stage = backend.stage
    assert stage.selected == []
    stage.select(selection_for(backend, operation="toggle", target="b"))
    stage.select(selection_for(backend, operation="toggle", target="c"))
    stage.select(selection_for(backend, operation="toggle", target="b"))
    assert stage.selected == ["c"]
    stage.select(selection_for(backend, operation="toggle", target="c"))
    assert stage.selected == []
    with pytest.raises(ValueError, match="选中"):
        stage.members("selected")
    stage.select(selection_for(backend, targets=["c", "b"]))
    assert stage.selected == ["b", "c"]
    stage.select(selection_for(backend, operation="order", order=list("dcba")))
    assert stage.selected == ["b", "c"] and stage.members("leftmost") == ["d"]
    motion = MotionController(backend)
    try:
        result = await run(motion, "stage_gather")
        assert result["status"] == "completed", result
        waiting = stage.positions()
        result = await run(motion, "stage_roll")
        assert result["status"] == "completed", result
        assert result["outcome"]["members"] == ["b", "c"]
        assert [r["member"] for r in result["outcome"]["results"]] == ["b", "c"]
        assert all(r["rotation_rad"] > 5 and r["returned"] for r in result["outcome"]["results"])
        assert all(
            math.dist(p, waiting[i]) < 0.12 for i, p in enumerate(stage.positions()) if i in {0, 3}
        )
        assert stage.selected == ["b", "c"]
        stage.select(selection_for(backend, targets=[]))
        result = await run(motion, "stage_roll")
        assert result["status"] == "failed" and "选中" in result["error"]
    finally:
        await motion.close()


async def test_multiselect_cancel_clears_all_rollers_without_reporting_completion(backend):
    motion = MotionController(backend)
    try:
        assert (await run(motion, "stage_gather"))["status"] == "completed"
        backend.stage.select(selection_for(backend, targets=["b", "c"]))
        a = Action(name="stage_roll")
        await motion.submit(a)
        await asyncio.sleep(0.1)
        await run(motion, "stop")
        assert (await motion.wait(a.request_id))["status"] == "cancelled"
        assert backend.stage.last_roll is None
        assert all(not d.command.any() and d.policy != "roulade" for d in backend.drivers)
    finally:
        await motion.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"targets": ["b", "b"]},
        {"targets": ["e"]},
        {"operation": "toggle", "targets": ["b"]},
        {"operation": "order", "target": "b"},
        {},
    ],
)
def test_selection_rejects_invalid_sets(backend, changes):
    with pytest.raises(ValidationError):
        selection_for(backend, **changes)


async def test_all_four_selected_roll_and_return_together(backend):
    motion = MotionController(backend)
    try:
        assert (await run(motion, "stage_gather"))["status"] == "completed"
        backend.stage.select(selection_for(backend, targets=list(MEMBERS)))
        result = await run(motion, "stage_roll")
        assert result["status"] == "completed", result
        assert result["outcome"]["members"] == list(MEMBERS)
        assert all(
            r["rotation_rad"] > 5 and r["standing"]["supported"]
            for r in result["outcome"]["results"]
        )
    finally:
        await motion.close()


@pytest.mark.parametrize(
    "values",
    [
        {"name": "stage_roll", "members": []},
        {"name": "stage_roll", "members": ["b", "b"]},
        {"name": "stage_roll", "members": ["b"], "member": "c"},
        {"name": "walk", "members": ["b"]},
    ],
)
def test_roll_member_sets_are_validated_before_motion(values):
    with pytest.raises(ValidationError):
        Action(**values)
