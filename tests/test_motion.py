import asyncio

import pytest
from pydantic import ValidationError

from duckking.motion import Action, MotionController, PreviewBackend


async def test_walk_is_bounded_and_returns_to_rest():
    backend = PreviewBackend()
    controller = MotionController(backend)
    action = Action(name="walk", duration=0.2, request_id="walk")
    await controller.submit(action)
    result = await controller.wait("walk")
    state = await backend.snapshot()
    assert result["status"] == "completed"
    assert 0 < state["pose"]["z"] < 0.05
    assert state["velocity"]["forward"] == 0
    assert state["physics"] is False


async def test_stop_preempts_and_does_not_resume_walk():
    controller = MotionController(PreviewBackend())
    await controller.submit(Action(name="walk", duration=3, request_id="walk"))
    await asyncio.sleep(0.06)
    await controller.submit(Action(name="stop", request_id="stop"))
    assert (await controller.wait("walk"))["status"] == "cancelled"
    assert (await controller.wait("stop"))["status"] == "completed"
    z = (await controller.backend.snapshot())["pose"]["z"]
    await asyncio.sleep(0.1)
    assert (await controller.backend.snapshot())["pose"]["z"] == z


async def test_request_retries_do_not_repeat_motion_and_conflicts_fail():
    controller = MotionController(PreviewBackend())
    action = Action(name="nod", duration=0.2, request_id="same")
    await controller.submit(action)
    task = controller.task
    await controller.submit(action)
    assert controller.task is task
    await controller.wait("same")
    assert (await controller.submit(action))["status"] == "completed"
    with pytest.raises(ValueError):
        await controller.submit(Action(name="walk", request_id="same"))


async def test_backend_failure_is_not_reported_as_success():
    class Broken(PreviewBackend):
        async def head(self, pitch):
            raise OSError("simulator disconnected")

    controller = MotionController(Broken())
    await controller.submit(Action(name="nod", request_id="broken"))
    result = await controller.wait("broken")
    assert result["status"] == "failed"
    assert "disconnected" in result["error"]
    assert controller.failure


@pytest.mark.parametrize("fields", [
    {"duration": 99}, {"duration": float("nan")}, {"speed": -1},
    {"name": "shell"}, {"unexpected": True},
])
def test_actions_reject_unbounded_or_unknown_input(fields):
    with pytest.raises(ValidationError):
        Action(**({"name": "walk"} | fields))
