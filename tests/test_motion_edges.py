import asyncio

from duckking.motion import Action, MotionController, PreviewBackend


async def test_immediate_stop_cancels_task_before_it_starts():
    controller = MotionController(PreviewBackend())
    await controller.submit(Action(name="walk", request_id="first"))
    await controller.submit(Action(name="stop", request_id="stop"))
    result = await asyncio.wait_for(controller.wait("first"), 1)
    assert result["status"] == "cancelled"
    await controller.wait("stop")
    await controller.close()


async def test_new_action_replaces_old_one_and_reset_restores_pose():
    controller = MotionController(PreviewBackend())
    await controller.submit(Action(name="walk", request_id="walk"))
    await asyncio.sleep(0.06)
    await controller.submit(Action(name="turn_left", duration=0.2, request_id="left"))
    await controller.wait("left")
    assert (await controller.backend.snapshot())["pose"]["yaw"] > 0
    await controller.submit(Action(name="turn_right", duration=0.2, request_id="right"))
    await controller.wait("right")
    await controller.submit(Action(name="reset", request_id="reset"))
    await controller.wait("reset")
    state = await controller.snapshot()
    assert state["backend"]["pose"] == {"x": 0, "z": 0, "yaw": 0, "pitch": 0}
    assert state["action"] is None
    await controller.close()


async def test_stop_failure_is_visible_and_cannot_be_claimed_completed():
    class BrokenStop(PreviewBackend):
        async def stop(self):
            raise OSError("stop acknowledgement missing")

    controller = MotionController(BrokenStop())
    await controller.submit(Action(name="nod", duration=0.2, request_id="head"))
    result = await controller.wait("head")
    assert result["status"] == "failed"
    assert "停止确认失败" in result["error"]


async def test_history_is_bounded():
    controller = MotionController(PreviewBackend())
    for i in range(205):
        await controller.submit(Action(name="stop", request_id=str(i)))
        await controller.wait(str(i))
    assert len(controller.records) == 200
    assert len(controller.done) == 200
    assert len(controller.events) == 60
    await controller.close()
