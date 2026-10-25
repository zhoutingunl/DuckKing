import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from duckking.mcp import DeviceMCP
from duckking.motion import Action, MotionController, PreviewBackend
from duckking.posture import measure_posture
from duckking.simulation import MuJoCoBackend

ASSETS = Path(__file__).resolve().parents[1] / "external"


@pytest.fixture
def backend():
    return MuJoCoBackend(ASSETS)


async def run(motion, name, **kwargs):
    action = Action(name=name, **kwargs)
    await motion.submit(action)
    return await motion.wait(action.request_id)


async def test_real_sit_holds_through_nod_stop_then_stands_and_walks(backend):
    motion = MotionController(backend)
    try:
        seated = await run(motion, "sit")
        assert seated["status"] == "completed"
        await run(motion, "nod")
        await run(motion, "stop")
        await asyncio.sleep(0.4)
        pose = measure_posture(backend, backend.drivers[0])
        assert pose["observed"] == "sit" and pose["supported"]
        assert 0.045 < pose["height_m"] < 0.078 and min(pose["knee_deg"]) > 57
        for name in ("walk", "turn_left", "kick_left"):
            result = await run(motion, name)
            assert result["status"] == "failed" and "站起来" in result["error"]
        assert (await run(motion, "stand"))["status"] == "completed"
        assert measure_posture(backend, backend.drivers[0])["observed"] == "stand"
        assert (await run(motion, "walk", duration=0.2))["status"] == "completed"
    finally:
        await motion.close()


async def test_cancelled_transitions_return_to_last_confirmed_posture(backend):
    motion = MotionController(backend)
    try:
        for name, rest in (("sit", "stand"), ("stand", "sit")):
            if name == "stand":
                assert (await run(motion, "sit"))["status"] == "completed"
            action = Action(name=name)
            await motion.submit(action)
            await asyncio.sleep(0.08)
            await run(motion, "stop")
            assert (await motion.wait(action.request_id))["status"] == "cancelled"
            assert backend.drivers[0].posture_target == rest
            assert not backend.drivers[0].command.any()
            await asyncio.sleep(1.3)
            assert measure_posture(backend, backend.drivers[0])["observed"] == rest
    finally:
        await motion.close()


async def test_dual_postures_are_targeted_and_exposed_as_real_mcp_results(backend):
    backend.load("duo")
    motion = MotionController(backend)
    mcp = DeviceMCP(motion, "sit-test")
    try:
        listing = await mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert {"duck_sit", "duck_stand"} <= {t["name"] for t in listing["result"]["tools"]}
        response = await mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "duck_sit", "arguments": {"target": "b"}},
            }
        )
        result = json.loads(response["result"]["content"][0]["text"])
        assert not response["result"]["isError"] and result["status"] == "completed"
        assert [measure_posture(backend, d)["observed"] for d in backend.drivers] == [
            "stand",
            "sit",
        ]
        assert (await run(motion, "duo_walk"))["status"] == "failed"
        assert (await run(motion, "sit", target="both"))["status"] == "completed"
        assert (await run(motion, "stand", target="both"))["status"] == "completed"
    finally:
        await mcp.close()
        await motion.close()


async def test_no_preview_sit_and_bounded_invalid_requests():
    motion = MotionController(PreviewBackend())
    try:
        for name in ("sit", "stand", "seated_show"):
            assert (await run(motion, name))["status"] == "failed"
        for args in (
            {"name": "sit", "duration": 4},
            {"name": "stand", "speed": 0.3},
            {"name": "seated_show", "target": "both"},
            {"name": "seated_show", "duration": 43},
        ):
            with pytest.raises(ValidationError):
                Action(**args)
    finally:
        await motion.close()


async def test_posture_failure_never_reports_success_or_keeps_new_intent(backend, monkeypatch):
    motion = MotionController(backend)
    # Inject a frozen physical state: a real transition must not be inferred
    # from the requested posture flag alone.
    monkeypatch.setattr(backend, "tick", lambda: None)
    try:
        result = await run(motion, "sit")
        assert result["status"] == "failed" and "时限" in result["error"]
        assert backend.drivers[0].posture_target == "stand"
        assert not backend.drivers[0].command.any()
    finally:
        await motion.close()


async def test_full_seated_choir_checks_all_four_stands_and_returns(backend):
    backend.load("seated")
    motion = MotionController(backend)
    try:
        result = await run(motion, "seated_show")
        assert result["status"] == "completed", result
        out = result["outcome"]
        assert out["verified"] and out["completed_solos"] == list("abcd")
        assert out["floor_contacts"] == [0] * 4 and all(out["table_contacts"])
        assert max(out["max_drift_m"]) < 0.12
        for i, (stand, sit) in enumerate(
            zip(out["standing_confirmations"], out["seated_returns"], strict=True)
        ):
            assert 4 + i * 8 < stand["at"] < 6 + i * 8
            assert 10 + i * 8 < sit["at"] < 12 + i * 8
            assert stand["height_m"] > 0.10 and sit["height_m"] < 0.078
            assert stand["upright"] > 0.94 and sit["upright"] > 0.94
            assert stand["supported"] and sit["supported"]
        assert all(d.rest_posture == "sit" and not d.command.any() for d in backend.drivers)
        assert (await run(motion, "seated_show"))["status"] == "failed"
        assert (await run(motion, "reset"))["status"] == "completed"
        assert backend.seated.phase == "ready"
    finally:
        await motion.close()


async def test_seated_show_cancellation_has_no_later_solo_or_standing_intents(backend):
    backend.load("seated")
    motion = MotionController(backend)
    try:
        action = Action(name="seated_show")
        await motion.submit(action)
        for _ in range(400):
            if backend.seated.phase == "solo":
                break
            await asyncio.sleep(0.02)
        assert backend.seated.phase == "solo"
        await run(motion, "stop")
        assert (await motion.wait(action.request_id))["status"] == "cancelled"
        await asyncio.sleep(1.3)
        assert backend.seated.phase == "stopped" and not backend.seated.completed_solos
        assert all(d.posture_target == "sit" and not d.command.any() for d in backend.drivers)
        assert all(measure_posture(backend, d)["observed"] == "sit" for d in backend.drivers)
        assert (await run(motion, "scene_ball"))["status"] == "completed"
        assert backend.seated is None
    finally:
        await motion.close()


@pytest.mark.parametrize('foot,rest', [('left', 0), ('right', 0), ('left', .6), ('right', .6)])
async def test_standing_then_kicking_transfers_to_trained_stance(backend, foot, rest):
    motion = MotionController(backend)
    try:
        assert (await run(motion, 'sit'))['status'] == 'completed'
        assert (await run(motion, 'stand'))['status'] == 'completed'
        if rest:
            await backend.wait_sim(rest)
        started = float(backend.data.time)
        result = await run(motion, 'kick_' + foot)
        assert result['status'] == 'completed', result
        assert result['outcome']['verified'] and foot in result['outcome']['contact_feet']
        assert result['outcome']['displacement_m'] > .02
        assert backend.data.time - started < 2.15
    finally:
        await motion.close()


async def test_cancel_during_posture_to_kick_handoff_never_starts_kick(backend, monkeypatch):
    motion = MotionController(backend)
    placed = []
    original = backend.place_ball

    def place(foot):
        placed.append(foot)
        original(foot)

    monkeypatch.setattr(backend, 'place_ball', place)
    try:
        assert (await run(motion, 'sit'))['status'] == 'completed'
        assert (await run(motion, 'stand'))['status'] == 'completed'
        action = Action(name='kick_left')
        await motion.submit(action)
        await backend.wait_sim(.1)
        await run(motion, 'stop')
        assert (await motion.wait(action.request_id))['status'] == 'cancelled'
        await backend.wait_sim(.5)
        assert not placed
        assert backend.drivers[0].policy == 'walk'
        assert not backend.drivers[0].command.any()
    finally:
        await motion.close()
