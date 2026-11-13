import asyncio
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from duckking.feature_backend import FeatureBackend
from duckking.feature_catalog import CATALOG
from duckking.feature_lifecycle import CONTINUOUS, FRESH_TRIAL, start_plan
from duckking.feature_worker import Worker


class World:
    """Lifecycle fixture only: it does not simulate robot physics."""

    def __init__(self):
        self.metrics = {}
        self.state = {"ducks": [{"id": "a", "fallen": False}]}
        self.started = []
        self.resets = 0
        self.stops = 0
        self.reset_started = asyncio.Event()
        self.reset_release = asyncio.Event()
        self.reset_release.set()
        self.perform_release = asyncio.Event()
        self.perform_release.set()
        self.reset_error = None
        self.blocked = {}

    def start_condition(self, action):
        if action in self.blocked:
            return {"mode": "blocked", "reason": self.blocked[action]}
        return None

    async def snapshot(self):
        return self.state

    async def perform(self, command):
        self.started.append(command.action)
        await self.perform_release.wait()
        return {"verified": True, "message": "fixture completed"}

    async def reset(self):
        self.resets += 1
        self.reset_started.set()
        await self.reset_release.wait()
        if self.reset_error:
            raise self.reset_error
        self.state["ducks"][0]["fallen"] = False

    async def stop(self):
        self.stops += 1


def request(action="run", *, operation="start", key="new"):
    return {"id": key, "command": {"operation": operation, "action": action, "request_id": key}}


def test_every_catalogue_entry_has_an_explicit_repeat_contract():
    assert FRESH_TRIAL.isdisjoint(CONTINUOUS)
    assert set(CATALOG) == FRESH_TRIAL | CONTINUOUS
    with pytest.raises(ValueError, match="连续动作"):
        start_plan(World(), "unknown", {}, {}, "run")


async def test_next_finite_trial_prepares_then_executes_and_keeps_previous_outcome():
    world, output = World(), io.StringIO()
    worker = Worker(world, "running", "rev", output)
    await worker.handle(request(key="first"))
    await worker.task
    previous = dict(worker.results[0])
    await worker.handle(request())
    assert worker.current["phase"] == "preparing" and not worker.current["restarted"]
    state = await worker.snapshot()
    assert not state["feature"]["actions"]["run"]["enabled"]
    await worker.task
    assert world.resets == 1 and world.started == ["run", "run"]
    assert worker.results[0] == previous
    assert worker.current["status"] == "completed" and worker.current["restarted"]
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    phases = [m["state"]["feature"]["phase"] for m in messages if m["type"] == "state"]
    assert phases.index("preparing") < len(phases) - 1 and phases[-1] == "completed"


async def test_continuous_commands_keep_the_scene_and_only_recover_a_fallen_duck():
    world = World()
    worker = Worker(world, "movement", "rev", io.StringIO())
    for key, action in [("a", "walk"), ("b", "backward")]:
        await worker.handle(request(action, key=key))
        await worker.task
    assert world.resets == 0
    world.state["ducks"][0]["fallen"] = True
    await worker.handle(request("nod", key="c"))
    await worker.task
    assert world.resets == 1 and world.started == ["walk", "backward", "nod"]
    assert worker.current["restarted"]


async def test_stop_waits_for_inflight_preparation_and_never_executes_its_old_command():
    world = World()
    world.reset_release.clear()
    worker = Worker(world, "running", "rev", io.StringIO())
    worker.current = {"status": "completed", "id": "old"}
    await worker.handle(request())
    await world.reset_started.wait()
    stop = asyncio.create_task(worker.handle(request(operation="stop", key="stop")))
    await asyncio.sleep(0)
    assert not stop.done()
    world.reset_release.set()
    await stop
    assert not world.started and worker.current["status"] == "cancelled"
    assert worker.task is None


async def test_replacement_waits_for_preparation_then_only_starts_latest_command():
    world = World()
    world.reset_release.clear()
    worker = Worker(world, "running", "rev", io.StringIO())
    worker.current = {"status": "completed", "id": "old"}
    await worker.handle(request(key="cancelled"))
    await world.reset_started.wait()
    replacement = asyncio.create_task(worker.handle(request(key="latest")))
    await asyncio.sleep(0)
    world.reset_release.set()
    await replacement
    await worker.task
    assert world.started == ["run"] and worker.current["id"] == "latest"
    assert [r["status"] for r in worker.results] == ["cancelled", "completed"]


async def test_immediate_stop_during_accepted_preparation_does_not_even_reset():
    world = World()
    worker = Worker(world, "running", "rev", io.StringIO())
    worker.current = {"status": "failed", "id": "old"}
    await worker.handle(request())
    await worker.handle(request(operation="stop", key="stop"))
    assert world.resets == 0 and not world.started
    assert worker.current["status"] == "cancelled"


async def test_unavailable_action_is_disabled_and_rejected_without_stopping_valid_work():
    world, output = World(), io.StringIO()
    world.blocked["undock"] = "请先回窝，再离窝。"
    world.perform_release.clear()
    worker = Worker(world, "dock", "rev", output)
    await worker.handle(request("dock"))
    before = world.stops
    state = await worker.snapshot()
    assert state["feature"]["actions"]["dock"]["enabled"]
    assert not state["feature"]["actions"]["undock"]["enabled"]
    await worker.handle(request("undock", key="blocked"))
    assert world.stops == before and worker.current["action"] == "dock"
    assert "请先回窝" in json.loads(output.getvalue().splitlines()[-1])["error"]
    await worker.cancel()


async def test_failed_preparation_requires_visible_recovery_without_claiming_completion():
    world, output = World(), io.StringIO()
    world.reset_error = ValueError("fixture reset failure")
    worker = Worker(world, "running", "rev", output)
    worker.current = {"status": "failed", "id": "old"}
    await worker.handle(request())
    await worker.task
    assert worker.current["status"] == "failed" and not world.started
    state = await worker.snapshot()
    assert state["feature"]["recovery_required"]
    assert not state["feature"]["actions"]["run"]["enabled"]
    await worker.handle(request(key="cannot-start"))
    assert "重新准备场景" in json.loads(output.getvalue().splitlines()[-1])["error"]
    world.reset_error = None
    await worker.handle(request(operation="reset"))
    assert not (await worker.snapshot())["feature"]["recovery_required"]


async def test_explicit_reset_failure_also_disables_actions_until_recovery():
    world, output = World(), io.StringIO()
    world.reset_error = ValueError("fixture reset failure")
    worker = Worker(world, "movement", "rev", output)
    await worker.handle(request(operation="reset"))
    state = await worker.snapshot()
    assert state["feature"]["recovery_required"]
    assert all(not a["enabled"] for a in state["feature"]["actions"].values())
    assert "重新准备场景" in json.loads(output.getvalue().splitlines()[-1])["error"]


@pytest.mark.parametrize("stop", [False, True])
async def test_hung_preparation_has_a_deadline_and_requests_process_termination(monkeypatch, stop):
    monkeypatch.setattr("duckking.feature_worker.RESET_TIMEOUT", 0.02)
    monkeypatch.setattr("duckking.feature_worker.RESET_CANCEL_TIMEOUT", 0.01)
    world, output = World(), io.StringIO()
    world.reset_release.clear()
    worker = Worker(world, "running", "rev", output)
    worker.current = {"status": "completed", "id": "old"}
    await worker.handle(request())
    await world.reset_started.wait()
    if stop:
        await worker.handle(request(operation="stop"))
    else:
        await asyncio.wait_for(worker.task, 1)
    assert not world.started and worker.stop_unconfirmed
    assert worker.current["status"] == "failed"
    assert any(m["type"] == "error" for m in map(json.loads, output.getvalue().splitlines()))


async def test_worker_stop_failure_is_fatal_not_a_ready_but_running_background_world():
    world, output = World(), io.StringIO()
    worker = Worker(world, "movement", "rev", output)
    await worker.handle(request("nod"))
    world.stop = AsyncMock(side_effect=ValueError("fixture stop failed"))
    await worker.task
    assert worker.current["status"] == "failed" and worker.stop_unconfirmed
    assert json.loads(output.getvalue().splitlines()[-1])["type"] == "error"


@pytest.mark.parametrize("state_frame", [False, True])
async def test_fatal_worker_error_terminates_the_process_and_fails_pending_calls(state_frame):
    backend = FeatureBackend("movement")
    backend.ready.set_result(True)
    stream = asyncio.StreamReader()
    process = SimpleNamespace(stdout=stream, returncode=None, wait=AsyncMock(return_value=-15))
    process.terminate = lambda: setattr(process, "returncode", -15)
    backend.process = process
    pending = asyncio.get_running_loop().create_future()
    backend.pending["pending"] = pending
    frame = ({"type": "state", "state": {"feature": {
        "stop_unconfirmed": True, "recovery_reason": "stop not confirmed"}}} if state_frame
        else {"type": "error", "message": "stop not confirmed"})
    stream.feed_data((json.dumps(frame) + "\n").encode())
    await backend._read()
    with pytest.raises(ValueError, match="stop not confirmed"):
        await pending
    assert backend.closed and process.returncode == -15
    assert not (await backend.snapshot())["connected"]


@pytest.mark.parametrize(
    ("connected", "action", "upright", "height", "mode"),
    [(False, "undock", 1, 0.125, "blocked"), (True, "dock", 1, 0.125, "blocked"),
     (False, "dock", 0.4, 0.125, "restart"), (False, "dock", 1, 0.05, "restart"),
     (False, "dock", 1, 0.125, "continue"), (True, "undock", 1, 0.05, "continue")],
)
def test_dock_dependencies_survive_automatic_restart(connected, action, upright, height, mode):
    from duckking.feature_dock import DockWorld

    world = SimpleNamespace(
        dk=SimpleNamespace(connected=lambda error: connected, tip_error=lambda *args: None),
        model=None, data=SimpleNamespace(qpos=[0, 0, height]), upright=lambda: upright,
    )
    assert DockWorld.start_condition(world, action)["mode"] == mode
