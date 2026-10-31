import asyncio
import base64
import gzip
import json
import struct
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from duckking.model_assets import pack_visual_model
from duckking.motion import Action, MotionController, PreviewBackend
from duckking.simulation import MuJoCoBackend
from duckking.table_choir import SHOW_DURATION, TABLE_HEIGHT, dance_command

ASSETS = Path(__file__).resolve().parents[1] / "external"


@pytest.fixture
def backend():
    backend = MuJoCoBackend(ASSETS)
    backend.load("table")
    return backend


async def test_four_ducks_sing_and_only_one_really_leaves_the_table_and_lands(backend):
    motion = MotionController(backend)
    assert len(backend.drivers) == 4
    assert all(backend.tabletop.supported)
    initial = [driver.pose(backend.data)[0].copy() for driver in backend.drivers]
    task = Action(name="table_show")
    await motion.submit(task)
    await asyncio.sleep(0.3)
    assert backend.tabletop.running
    result = await motion.wait(task.request_id)
    assert result["status"] == "completed", json.dumps(result, ensure_ascii=False)
    out = result["outcome"]
    assert out["verified"] and not out["running"]
    assert 16 < out["dropped_at"] <= out["landed_at"] < SHOW_DURATION
    assert out["supported"] == [True, True, True, False]
    assert all(out["table_contacts"])
    assert out["ground_contacts"][:3] == [0, 0, 0] and out["ground_contacts"][3] > 0
    assert out["min_root_height_m"][3] < TABLE_HEIGHT - 0.2
    assert all(min(pair) > 25 for pair in out["knee_excursion_deg"])
    assert all(min(pair) > 0.012 for pair in out["ankle_vertical_excursion_m"])
    assert max(out["dance_max_drift_m"]) < 0.14
    floor = out["floor_dance"]
    assert out["landed_at"] + 1.5 < floor["started_at"] < SHOW_DURATION - 5
    assert min(floor["knee_excursion_deg"]) > 25
    assert min(floor["ankle_vertical_excursion_m"]) > 0.012
    assert floor["max_drift_m"] < 0.14
    final = [driver.pose(backend.data)[0].copy() for driver in backend.drivers]
    # Ground impacts may bounce the root back under the table edge. Actual
    # loss of table support, height loss and floor contacts prove the fall.
    assert final[3][0] - initial[3][0] > 0.08 and initial[3][0] < 0.45
    assert initial[3][2] - final[3][2] > 0.25
    assert all(p[2] > TABLE_HEIGHT for p in final[:3])
    assert all(not driver.command.any() for driver in backend.drivers)
    # A second click cannot claim the same completed fall as a new result.
    replay = Action(name="table_show")
    await motion.submit(replay)
    assert (await motion.wait(replay.request_id))["status"] == "failed"
    revision = backend.revision
    await backend.reset()
    assert backend.revision == revision and backend.tabletop.phase == "ready"
    assert all(backend.tabletop.supported) and backend.tabletop.dropped_at is None
    await motion.close()


async def test_table_stop_and_scene_switch_cancel_commands_without_replaying_fall(backend):
    motion = MotionController(backend)
    for replacement in ("stop", "scene_duo"):
        backend.load("table")
        show = Action(name="table_show")
        await motion.submit(show)
        await asyncio.sleep(0.12)
        stopped = Action(name=replacement)
        await motion.submit(stopped)
        await motion.wait(stopped.request_id)
        assert (await motion.wait(show.request_id))["status"] == "cancelled"
        assert all(not driver.command.any() for driver in backend.drivers)
        if replacement == "stop":
            assert backend.tabletop.phase == "stopped"
            assert backend.tabletop.dropped_at is None
    await motion.close()


async def test_invalid_table_state_and_solver_failure(backend, monkeypatch):
    motion = MotionController(backend)
    wrong = Action(name="walk")
    await motion.submit(wrong)
    assert (await motion.wait(wrong.request_id))["status"] == "failed"
    backend.tabletop.supported[3] = False
    with pytest.raises(ValueError, match="四只鸭"):
        await backend.tabletop.perform()
    backend.load("ball")
    show = Action(name="table_show")
    await motion.submit(show)
    assert (await motion.wait(show.request_id))["status"] == "failed"
    backend.load("table")
    show = Action(name="table_show")
    await motion.submit(show)
    await asyncio.sleep(0.08)
    monkeypatch.setattr(backend, "tick", lambda: (_ for _ in ()).throw(ValueError("solver")))
    assert (await motion.wait(show.request_id))["status"] == "failed"
    assert not backend.tabletop.running and all(not d.command.any() for d in backend.drivers)
    await motion.close()
    preview = MotionController(PreviewBackend())
    task = Action(name="table_show")
    await preview.submit(task)
    assert (await preview.wait(task.request_id))["status"] == "failed"
    await preview.close()


async def test_dance_position_guard_cancels_and_clears_all_intents(backend, monkeypatch):
    driver = backend.drivers[0]
    pose = driver.pose

    def displaced(data):
        position, yaw = pose(data)
        position = position.copy()
        position[0] += 0.2
        return position, yaw

    monkeypatch.setattr(driver, "pose", displaced)
    with pytest.raises(ValueError, match="偏离站位"):
        await backend.tabletop.perform()
    assert not backend.tabletop.running
    assert all(not d.command.any() for d in backend.drivers)
    monkeypatch.setattr(driver, "pose", pose)
    for elapsed in np.linspace(0, 15.9, 100):
        driver.command[:] = 0
        dance_command(driver, backend.data, 0, elapsed)
        assert np.linalg.norm(driver.command[:2]) <= 0.46
        assert abs(driver.command[2]) <= 0.5
        if driver.command[:2].any():
            assert not driver.command[9:12].any()


@pytest.mark.parametrize(
    "changes",
    [
        {"duration": 999},
        {"duration": 35},
        {"speed": 0.2},
        {"target": "b"},
    ],
)
def test_table_choreography_has_a_fixed_bounded_duration(changes):
    with pytest.raises(ValidationError):
        Action(name="table_show", **changes)
    assert Action(name="table_show").duration == SHOW_DURATION
    with pytest.raises(ValidationError):
        Action(name="walk", duration=SHOW_DURATION)


def test_four_duck_geometry_shares_bytes_but_keeps_every_geom_and_exact_mesh(backend):
    original = backend.geometry()
    assert {g["duck"] for g in original["geoms"] if g["part"] == "top_head_shell"} == set("abcd")
    assert all(g["duck"] is None for g in original["geoms"]
               if backend.model.geom(g["id"]).name.startswith("table_"))
    packed = pack_visual_model({**original, "physics": True})
    size = struct.unpack_from("<I", packed, 4)[0]
    meta = json.loads(packed[8 : 8 + size])
    start = 8 + (size + 3) // 4 * 4
    assert meta["geoms"] == original["geoms"] and len(meta["geoms"]) > 280
    shared = set()
    for key, mesh in meta["meshes"].items():
        shared.add((mesh["vertices"]["offset"], mesh["faces"]["offset"]))
        for name, dtype in (("vertices", "<f4"), ("faces", "<u4")):
            expected = np.frombuffer(base64.b64decode(original["meshes"][int(key)][name]), dtype)
            info = mesh[name]
            actual = np.frombuffer(
                packed,
                dtype if name == "vertices" else f"<u{info['bytes']}",
                count=info["count"],
                offset=start + info["offset"],
            )
            np.testing.assert_array_equal(expected, actual)
    assert len(shared) < len(meta["meshes"]) / 2
    assert len(gzip.compress(packed)) < 4_000_000


async def test_cancelled_cold_compile_is_reused_and_cannot_change_scene_later(monkeypatch):
    import threading

    backend = MuJoCoBackend(ASSETS)
    motion = MotionController(backend)
    entered, release = threading.Event(), threading.Event()
    build = backend._build
    calls = []

    def slow(scene):
        calls.append(scene)
        entered.set()
        assert release.wait(10), "test did not release compiler"
        return build(scene)

    monkeypatch.setattr(backend, "_build", slow)
    first = Action(name="scene_table")
    try:
        await motion.submit(first)
        assert await asyncio.to_thread(entered.wait, 3)
        await motion.submit(Action(name="stop"))
        assert (await motion.wait(first.request_id))["status"] == "cancelled"
        assert backend.scene == "ball"
        second = Action(name="scene_table")
        await motion.submit(second)
        await asyncio.sleep(0.05)
        assert calls == ["table"] and backend.scene == "ball"
        release.set()
        assert (await motion.wait(second.request_id))["status"] == "completed"
        assert backend.scene == "table" and all(backend.tabletop.supported)
        assert calls == ["table"]
    finally:
        release.set()
        await motion.close()


@pytest.mark.parametrize("idle_ticks", [0, 1, 2, 50, 150, 300])
async def test_table_departure_is_independent_of_async_observer_cadence(backend, idle_ticks):
    proofs = []
    for burst in (1, 4):
        backend.load("table")
        for _ in range(idle_ticks):
            backend.tick()

        async def paced_loop(batch=burst):
            # Change only event-loop pacing. Physics is still 5 ms integration
            # and policy commands are sampled every 20 ms in both cases.
            while True:
                for _ in range(batch):
                    backend.tick()
                await asyncio.sleep(0.001)

        backend._loop = paced_loop
        motion = MotionController(backend)
        try:
            action = Action(name="table_show")
            await motion.submit(action)
            result = await motion.wait(action.request_id)
            assert result["status"] == "completed", result
            out = result["outcome"]
            assert out["ground_contacts"][:3] == [0, 0, 0]
            assert out["floor_dance"]["started_at"] is not None
            assert min(out["floor_dance"]["knee_excursion_deg"]) > 25
            proofs.append((out["dropped_at"], out["landed_at"], out["floor_dance"]["started_at"]))
        finally:
            await motion.close()
    np.testing.assert_allclose(proofs[0], proofs[1], atol=0.021, rtol=0)


def test_departure_rejects_missing_stable_support_without_moving_root(backend):
    table = backend.tabletop
    table.running = True
    table.sim_start = float(backend.data.time) - 16.1
    initial = backend.data.qpos.copy()
    with pytest.raises(ValueError, match="离桌前未确认站稳"):
        table.step()
    assert not backend.drivers[3].command.any()
    np.testing.assert_array_equal(backend.data.qpos, initial)


def test_table_landing_with_ci_idle_phase_clears_table_leg_before_dancing(backend):
    # Reproduces CI's exact 4.22 s start: on Linux the old controller stopped
    # at 34.88 s with 0.1439368 m floor drift after landing beside the table leg.
    for _ in range(151):
        backend.tick()
    table = backend.tabletop
    table.running = True
    table.sim_start = float(backend.data.time)
    assert table.sim_start == pytest.approx(4.22)
    for _ in range(1801):
        backend.tick()
    out = table.snapshot()
    assert 16 < out["dropped_at"] <= out["landed_at"] < 20
    assert out["supported"] == [True, True, True, False]
    assert out["ground_contacts"][:3] == [0, 0, 0] and out["ground_contacts"][3] > 0
    assert out["floor_dance"]["started_at"] < SHOW_DURATION - 5
    assert min(out["floor_dance"]["knee_excursion_deg"]) > 25
    assert min(out["floor_dance"]["ankle_vertical_excursion_m"]) > 0.012
    assert out["floor_dance"]["max_drift_m"] < 0.14


def test_landing_follow_through_is_bounded_world_outward_and_never_moves_root(backend):
    table = backend.tabletop
    table.running = True
    table.dropped_at = 17.4
    table.landed_at = 17.5
    table.sim_start = float(backend.data.time) - 17.6
    driver = backend.drivers[3]
    backend.data.qpos[driver.root + 3:driver.root + 7] = [np.cos(0.6), 0, 0, np.sin(0.6)]
    initial = backend.data.qpos.copy()
    table.step()
    _, yaw = driver.pose(backend.data)
    forward, sideways = driver.command[:2]
    np.testing.assert_allclose(
        [np.cos(yaw) * forward - np.sin(yaw) * sideways,
         np.sin(yaw) * forward + np.cos(yaw) * sideways], [0.35, 0], atol=1e-7,
    )
    assert np.linalg.norm(driver.command[:2]) == pytest.approx(0.35)
    np.testing.assert_array_equal(backend.data.qpos, initial)
    backend.data.time += 0.4
    table.step()
    assert not driver.command.any()
    table.stop()
    assert not table.running
