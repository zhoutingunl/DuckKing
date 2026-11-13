import asyncio
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from duckking.app import create_app
from duckking.feature_backend import FeatureBackend
from duckking.feature_catalog import CATALOG, FeatureCommand
from duckking.feature_worker import Worker
from duckking.mcp import DeviceMCP
from duckking.motion import MotionController


class World:
    def __init__(self):
        self.metrics = {}
        self.started = asyncio.Event()
        self.released = asyncio.Event()
        self.stops = 0
        self.resets = 0
        self.exit = asyncio.Event()
        self.failure = None

    async def perform(self, command):
        self.started.set()
        try:
            await self.released.wait()
            if self.failure:
                raise self.failure
            return {"verified": True, "message": "completed"}
        finally:
            self.exit.set()

    async def stop(self):
        self.stops += 1

    async def reset(self):
        assert self.exit.is_set()
        self.resets += 1

    async def snapshot(self):
        return {"physics": True}


def command(operation="start", **kwargs):
    return {
        "id": "rpc",
        "command": {"operation": operation, "action": "hop", "request_id": "once", **kwargs},
    }


@pytest.mark.parametrize(
    "arguments",
    [
        {"duration": 100},
        {"duration": -1},
        {"speed": float("nan")},
        {"speed": float("inf")},
        {"order": ["a"] * 9},
        {"script": "anything"},
        {"operation": "exec"},
        {"action": "walk"},
        {"order": ["e"]},
    ],
)
def test_feature_commands_reject_unbounded_unknown_and_wrong_scene(arguments):
    with pytest.raises(ValueError):
        FeatureCommand.model_validate({"action": "hop", **arguments}).check("hop")


def test_catalogue_covers_ten_groups_without_claiming_hardware_charging():
    assert {x["group"] for x in CATALOG.values()} == set(range(1, 11))
    assert len(CATALOG) == 41
    assert CATALOG["dock"]["observation"] == "simulated_tag_and_proprioception"
    assert CATALOG["soccer"]["observation"] == "rgb"


async def test_stop_cancels_physics_before_reply_and_preserves_cancelled_result():
    world = World()
    output = io.StringIO()
    worker = Worker(world, "hop", "revision", output)
    await worker.handle(command())
    await world.started.wait()
    await worker.handle(command("stop"))
    assert world.exit.is_set() and world.stops >= 2
    assert worker.task is None
    assert worker.current["status"] == "cancelled"
    assert worker.results[-1]["verified"] is False
    assert json.loads(output.getvalue().splitlines()[-1])["result"]["status"] == "cancelled"


async def test_cancel_before_task_first_turn_still_produces_terminal_result():
    world = World()
    worker = Worker(world, "hop", "rev", io.StringIO())
    await worker.handle(command())
    await worker.handle(command("stop"))
    assert not world.started.is_set()
    assert len(worker.results) == 1
    assert worker.results[0]["status"] == "cancelled"


async def test_acceptance_is_published_before_reply_and_before_policy_first_turn():
    world, output = World(), io.StringIO()
    worker = Worker(world, "hop", "rev", output)
    await worker.handle(command())
    assert not world.started.is_set()
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [message["type"] for message in messages] == ["state", "reply"]
    assert messages[0]["state"]["feature"]["status"] == "running"
    assert messages[0]["state"]["feature"]["id"] == messages[1]["result"]["id"]
    await worker.cancel()


async def test_reset_waits_for_old_task_and_does_not_automatically_restart():
    world = World()
    worker = Worker(world, "hop", "rev", io.StringIO())
    await worker.handle(command())
    await world.started.wait()
    await worker.handle(command("reset"))
    assert world.resets == 1 and worker.task is None
    assert worker.current["status"] == "idle"


async def test_failed_physics_is_never_reported_completed():
    world = World()
    world.failure = ValueError("unstable contact")
    world.released.set()
    worker = Worker(world, "hop", "rev", io.StringIO())
    await worker.handle(command())
    await worker.task
    assert worker.current["status"] == "failed"
    assert worker.current["message"] == "unstable contact"
    assert world.stops >= 2


@pytest.mark.parametrize("raw", [b"{}", b"[]\n", b"{broken}\n", b"x" * 16385 + b"\n"])
async def test_worker_rejects_incomplete_overlong_and_invalid_frames(raw):
    reader = asyncio.StreamReader(limit=16384)
    reader.feed_data(raw)
    reader.feed_eof()
    worker = Worker(World(), "hop", "rev", io.StringIO())
    with pytest.raises(ValueError):
        await worker.receive(reader)
    assert worker.task is None


async def test_bad_command_keeps_protocol_usable_for_next_status():
    reader = asyncio.StreamReader()
    bad = command(action="exec")
    good = command("status")
    reader.feed_data((json.dumps(bad) + "\n" + json.dumps(good) + "\n").encode())
    reader.feed_eof()
    output = io.StringIO()
    worker = Worker(World(), "hop", "rev", output)
    await worker.receive(reader)
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert "error" in messages[0]
    assert messages[1]["result"]["status"] == "idle"


async def test_repeated_request_is_not_reexecuted_and_conflicting_id_rejected():
    backend = FeatureBackend("hop")
    backend.rpc = AsyncMock(return_value={"status": "running"})
    payload = {"action": "hop", "request_id": "repeat"}
    await asyncio.gather(backend.invoke(payload), backend.invoke(payload))
    assert backend.rpc.await_count == 1
    with pytest.raises(ValueError, match="ID"):
        await backend.invoke({**payload, "duration": 4})
    await backend.close()


async def test_worker_crash_fails_pending_request_without_preview_fallback():
    backend = FeatureBackend("hop")
    stream = asyncio.StreamReader()
    backend.process = SimpleNamespace(stdout=stream, returncode=1)
    pending = asyncio.get_running_loop().create_future()
    backend.pending["waiting"] = pending
    stream.feed_eof()
    await backend._read()
    with pytest.raises(ValueError, match="物理进程"):
        await backend.ready
    with pytest.raises(ValueError, match="物理进程"):
        await pending
    state = await backend.snapshot()
    assert not state["connected"] and state["kind"] == "mujoco"
    await backend.close()


async def test_feature_voice_tools_are_scoped_and_status_excludes_camera_bytes():
    backend = FeatureBackend("hop")
    backend.state = {"feature": {"status": "idle"}, "geoms": [1], "sensors": {"image": "pixels"}}
    mcp = DeviceMCP(MotionController(backend), "test")
    listing = await mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = listing["result"]["tools"]
    assert {t["name"] for t in tools} == {"duck_feature", "duck_stop", "duck_get_status"}
    schema = next(t for t in tools if t["name"] == "duck_feature")["inputSchema"]
    assert schema["properties"]["action"]["enum"] == ["hop"]
    denied = await mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "duck_walk_short", "arguments": {}},
        }
    )
    assert denied["result"]["isError"]
    status = await mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "duck_get_status", "arguments": {}},
        }
    )
    assert "pixels" not in str(status)
    await backend.close()


def test_feature_api_missing_assets_fails_clearly_and_releases_preparation(monkeypatch):
    monkeypatch.setattr(
        FeatureBackend, "create", AsyncMock(side_effect=ValueError("assets missing"))
    )
    app = create_app()
    with TestClient(app) as client:
        assert len(client.get("/api/features/catalog").json()["capabilities"]) == 41
        response = client.post("/api/features/prepare", json={"capability": "hop"})
        assert response.status_code == 503
        assert app.state.rooms["1"].scene_motion is None
        assert app.state.rooms["1"].preparing is None
        assert client.post("/api/features/command", json={"action": "hop"}).status_code == 409
        assert client.get("/api/features/emotion-audio/unknown.wav").status_code == 404


def test_rgb_perception_rejects_border_background_and_combined_objects():
    np = pytest.importorskip("numpy")
    pytest.importorskip("mujoco")
    from duckking.feature_senses import color_observation

    pixels = np.zeros((240, 320, 3), dtype=np.uint8)
    pixels[:100, :, 2] = 200  # Blue sky touches the image boundary.
    yy, xx = np.ogrid[:240, :320]
    pixels[(xx - 200) ** 2 + (yy - 160) ** 2 <= 15**2] = [0, 0, 220]
    pixels[(xx - 50) ** 2 + (yy - 180) ** 2 <= 8**2] = [0, 0, 220]
    observation = color_observation(pixels, "blue")
    assert observation["x"] == pytest.approx(200)
    assert observation["y"] == pytest.approx(160)
    assert 650 < observation["area"] < 750
    assert color_observation(pixels, "red") is None


def test_rgb_position_uses_camera_and_robot_frames_not_ball_truth():
    np = pytest.importorskip("numpy")
    pytest.importorskip("mujoco")
    from duckking.feature_senses import rgb_sphere_position

    found = {"x": 160, "y": 120, "radius": 20}
    result = rgb_sphere_position(
        found, 0.035, np.array([0.05, 0, 0.2]), np.eye(3), np.zeros(3), np.eye(3), focal=200
    )
    assert result == pytest.approx([0.05, 0, -0.15])


def test_navigation_path_respects_inflated_obstacle_and_reaches_named_goal():
    pytest.importorskip("mujoco")
    from duckking.feature_senses import map_path

    path = map_path([0, 0], [0.8, -0.35])
    assert path[-1] == pytest.approx([0.8, -0.35])
    for x, y in path:
        assert not (abs(x - 0.38) < 0.22 and abs(y + 0.02) < 0.24)
    assert all(
        abs(a[0] - b[0]) + abs(a[1] - b[1]) == pytest.approx(0.05)
        for a, b in zip(path, path[1:], strict=False)
    )


def test_functional_release_verification_rejects_modified_files_and_paths(tmp_path):
    import hashlib
    import runpy

    script = runpy.run_path("scripts/fetch_feature_assets.py")
    verify = script["verify_package"]
    expected = {
        name: {"repository": repo, "revision": rev}
        for name, (repo, rev, _) in script["REPOS"].items()
    }
    expected.update(
        {
            "policies/" + name: {"repository": repo, "revision": rev}
            for name, (repo, rev, _) in script["MODELS"].items()
        }
    )
    data = b"fixed model"
    (tmp_path / "policy.onnx").write_bytes(data)
    manifest = {"sources": expected, "sha256": {"policy.onnx": hashlib.sha256(data).hexdigest()}}
    (tmp_path / "sources.json").write_text(json.dumps(manifest))
    verify(tmp_path)
    (tmp_path / "policy.onnx").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        verify(tmp_path)
    manifest["sha256"] = {"../policy.onnx": "0" * 64}
    (tmp_path / "sources.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="path"):
        verify(tmp_path)


@pytest.mark.anonymous_rooms
def test_functional_actions_cannot_cross_visitor_room_ownership():
    app = create_app()
    with TestClient(app) as one, TestClient(app) as two:
        first = one.post("/api/rooms/claim").json()["room"]
        second = two.post("/api/rooms/claim").json()["room"]
        assert first != second
        for endpoint, data in [("prepare", {"capability": "hop"}), ("command", {"action": "hop"})]:
            response = two.post(f"/api/features/{endpoint}?room={first}", json=data)
            assert response.status_code in {403, 404}
        assert app.state.rooms[first].scene_motion is None


async def test_dock_charge_survives_per_task_metrics_reset(monkeypatch):
    pytest.importorskip("mujoco")
    import numpy as np

    from duckking.feature_dock import DockWorld

    world = DockWorld.__new__(DockWorld)
    world.model = world.bam = None
    world.data = SimpleNamespace(time=2.0, qpos=np.zeros(7))
    world.pol = SimpleNamespace(set_vel_cmd=lambda *args: None)
    world.dg = SimpleNamespace(step_control=lambda *args, **kwargs: None)
    connected = [True]
    world.dk = SimpleNamespace(
        tip_error=lambda *args: np.zeros(3), connected=lambda error: connected[0]
    )
    world.virtual_battery_percent = 20.0
    world.metrics = {}  # Worker clears per-command telemetry before starting.
    monkeypatch.setattr("duckking.feature_dock.asyncio.sleep", AsyncMock())
    await world.ticks(100, "charging")
    assert world.metrics["virtual_battery_percent"] == pytest.approx(22)
    world.metrics = {}
    connected[0] = False
    await world.ticks(100, "charging")
    assert world.metrics["virtual_battery_percent"] == pytest.approx(22)
    assert world.metrics["charging_proxy"] is False


def test_voice_schema_only_advertises_parameters_used_by_the_current_skill():
    from duckking.feature_catalog import voice_tools

    def properties(capability):
        return voice_tools(capability)[0]["inputSchema"]["properties"]

    assert {"duration", "speed"} <= properties("movement").keys()
    assert "order" not in properties("movement")
    assert properties("director")["order"]["items"]["enum"] == list("abcd")
    for capability in CATALOG:
        if capability != "movement":
            assert not {"duration", "speed"} & properties(capability).keys()
        if capability != "director":
            assert "order" not in properties(capability)


@pytest.mark.parametrize(("emotion", "file"), [("no", "no_a"), ("angry", "angry_a")])
def test_official_emotion_audio_variant_routes(monkeypatch, tmp_path, emotion, file):
    folder = tmp_path / "features/emotions/sounds"
    folder.mkdir(parents=True)
    content = b"RIFF-test-audio-route"
    (folder / f"{file}.wav").write_bytes(content)
    monkeypatch.setenv("DUCKKING_SIM_DIR", str(tmp_path))
    with TestClient(create_app()) as client:
        response = client.get(f"/api/features/emotion-audio/{emotion}.wav")
        assert response.status_code == 200 and response.content == content
        assert response.headers["content-type"].startswith("audio/wav")
        assert client.get("/api/features/emotion-audio/unknown.wav").status_code == 404


def test_bad_height_is_rejected_before_replacing_a_room_world(monkeypatch):
    create = AsyncMock(side_effect=ValueError("not reached"))
    monkeypatch.setattr(FeatureBackend, "create", create)
    with TestClient(create_app()) as client:
        for payload in [dict(capability="stilts", variant=11), dict(capability="hop", variant=10)]:
            assert client.post("/api/features/prepare", json=payload).status_code == 422
        assert not create.called
        assert client.get("/api/features/catalog?sort=invalid").status_code == 422
        legacy = client.get("/api/features/catalog?metric=clicks").json()
        assert legacy["ranking"]["metric"] == "engagement"


def test_explicit_reprepare_releases_matching_old_world_and_never_falls_back(monkeypatch):
    create = AsyncMock(side_effect=ValueError("new world unavailable"))
    monkeypatch.setattr(FeatureBackend, "create", create)
    app = create_app()
    with TestClient(app) as client:
        old = SimpleNamespace(
            backend=SimpleNamespace(
                scene="functional", capability="hop", variant=None, error=None, closed=False
            ),
            snapshot=AsyncMock(return_value={"backend": {"scene": "functional"}}),
            close=AsyncMock(),
        )
        app.state.rooms["1"].scene_motion = old
        assert client.post("/api/features/prepare", json={"capability": "hop"}).status_code == 200
        assert not create.called and not old.close.called
        response = client.post("/api/features/prepare", json={"capability": "hop", "replace": True})
        assert response.status_code == 503
        assert old.close.await_count == 1 and create.await_count == 1
        assert app.state.rooms["1"].scene_motion is None
