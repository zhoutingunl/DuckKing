import asyncio
import json

import pytest

from duckking.mcp import DeviceMCP
from duckking.motion import MotionController, PreviewBackend


def request(method, params=None, ident=1):
    return {"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}}


async def test_discovery_protocol_errors_and_status():
    motion = MotionController(PreviewBackend())
    mcp = DeviceMCP(motion, "test")
    assert await mcp.handle({"method": "notifications/initialized"}) is None
    assert "error" in await mcp.handle({"jsonrpc": "bad", "id": [], "method": "tools/list"})
    response = await mcp.handle(request("initialize"))
    assert response["result"]["capabilities"] == {"tools": {}}
    listing = await mcp.handle(request("tools/list", ident=2))
    assert {tool["name"] for tool in listing["result"]["tools"]} == {
        "duck_nod",
        "duck_walk_short",
        "duck_turn_left",
        "duck_turn_right",
        "duck_stop",
        "duck_get_status",
        "duck_flash_step",
        "duck_bear_shake",
        "duck_backward", "duck_strafe_left", "duck_strafe_right",
        "duck_shake_head", "duck_tilt_head",
    }
    assert "error" in await mcp.handle(request("not-a-method", ident=3))
    assert "error" in await mcp.handle(request("tools/call", [1], ident=4))
    status = await mcp.handle(request("tools/call", {"name": "duck_get_status"}, ident=5))
    assert "preview" in status["result"]["content"][0]["text"]
    await mcp.close()


async def test_duplicate_calls_are_shared_and_conflicts_do_not_repeat():
    motion = MotionController(PreviewBackend())
    mcp = DeviceMCP(motion, "test")
    call = request("tools/call", {"name": "duck_walk_short", "arguments": {"duration": 0.2}})
    results = await asyncio.gather(mcp.handle(call), mcp.handle(call))
    assert results[0] == results[1]
    assert len(motion.records) == 1
    assert results[0]["result"]["isError"] is False
    assert (await mcp.handle(request("tools/list")))["error"]["message"] == "Request ID reused"
    await motion.close()


async def test_stop_interrupts_an_inflight_mcp_action():
    motion = MotionController(PreviewBackend())
    mcp = DeviceMCP(motion, "test")
    walk = asyncio.create_task(mcp.handle(request("tools/call", {"name": "duck_walk_short"})))
    await asyncio.sleep(0.06)
    stop = await mcp.handle(request("tools/call", {"name": "duck_stop"}, ident=2))
    cancelled = await walk
    assert stop["result"]["isError"] is False
    assert cancelled["result"]["isError"] is True
    assert json.loads(cancelled["result"]["content"][0]["text"])["status"] == "cancelled"
    await motion.close()


@pytest.mark.parametrize(
    "params",
    [
        {"name": "shell"},
        {"name": "duck_nod", "arguments": {"command": "bad"}},
        {"name": "duck_nod", "arguments": []},
        {"name": "duck_walk_short", "arguments": {"duration": 100}},
        {"name": "duck_turn_left", "arguments": {"duration": 0.1}},
        {"name": "duck_turn_right", "arguments": {"duration": 4}},
        {"name": "duck_turn_left", "arguments": {"angle": 90}},
    ],
)
async def test_invalid_tools_and_arguments_produce_tool_errors(params):
    mcp = DeviceMCP(MotionController(PreviewBackend()), "test")
    assert (await mcp.handle(request("tools/call", params)))["result"]["isError"] is True


async def test_replay_cache_is_bounded_and_session_closes_pending_tasks():
    motion = MotionController(PreviewBackend())
    mcp = DeviceMCP(motion, "test")
    for index in range(205):
        await mcp.handle(request("tools/list", ident=index))
    assert len(mcp.requests) == 200
    call = asyncio.create_task(mcp.handle(request("tools/call", {"name": "duck_nod"}, ident=999)))
    await asyncio.sleep(0.01)
    await mcp.close()
    with pytest.raises(asyncio.CancelledError):
        await call
    await motion.close()


async def test_flash_tool_executes_choreography_and_retries_do_not_replay():
    motion = MotionController(PreviewBackend())
    mcp = DeviceMCP(motion, "choreo")
    call = request("tools/call", {"name": "duck_flash_step"})
    first, second = await asyncio.gather(mcp.handle(call), mcp.handle(call))
    assert first == second
    result = json.loads(first["result"]["content"][0]["text"])
    assert result["name"] == "flash_step" and result["status"] == "completed"
    assert len(motion.records) == 1
    assert {
        event["text"].split(" · ")[-1] for event in motion.events if event["kind"] == "phase"
    } == {"预备", "左闪", "回闪", "收势"}
    await motion.close()


async def test_bear_tool_can_be_stopped_by_another_tool_call():
    motion = MotionController(PreviewBackend())
    mcp = DeviceMCP(motion, "choreo")
    dance = asyncio.create_task(mcp.handle(request("tools/call", {"name": "duck_bear_shake"})))
    await asyncio.sleep(0.1)
    await mcp.handle(request("tools/call", {"name": "duck_stop"}, ident=2))
    assert (await dance)["result"]["isError"] is True
    assert (await motion.backend.snapshot())["pose"]["body_z"] == 0
    await motion.close()


async def test_sequential_walk_left_right_directions_and_deduplicated_measurements():
    class ObservedPreview(PreviewBackend):
        def __init__(self):
            super().__init__()
            self.commands = []

        async def move(self, forward, turn, lateral=0):
            self.commands.append((forward, turn))
            await super().move(forward, turn, lateral)

    backend = ObservedPreview()
    motion = MotionController(backend)
    mcp = DeviceMCP(motion, "sequence")
    events = []

    def observe(event, **fields):
        events.append((event, fields))

    for ident, name in enumerate(["duck_walk_short", "duck_turn_left", "duck_turn_right"]):
        call = request("tools/call", {"name": name, "arguments": {"duration": .2}}, ident)
        result = await mcp.handle(call, observe=observe)
        assert not result["result"]["isError"]
        assert await mcp.handle(call, observe=observe) == result
    assert [e[1]["tool"] for e in events if e[0] == "action_start"] == [
        "duck_walk_short", "duck_turn_left", "duck_turn_right"
    ]
    assert len(events) == 6
    assert all(e[1]["result"] == "completed" for e in events if e[0] == "action_end")
    assert any(v > 0 and y == 0 for v, y in backend.commands)
    assert any(v == 0 and y > 0 for v, y in backend.commands)
    assert any(v == 0 and y < 0 for v, y in backend.commands)
    await motion.close()
