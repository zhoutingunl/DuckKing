import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from duckking.motion import Action, MotionController, PreviewBackend
from duckking.studio import Routine, Studio

ASSETS = Path(__file__).resolve().parents[1] / "external"


@pytest.fixture
async def studio(tmp_path):
    motion = MotionController(PreviewBackend())
    studio = Studio(motion, tmp_path)
    motion.studio = studio
    await studio.select("director")
    yield studio
    await motion.close()


async def test_replace_cancels_remaining_steps_and_retains_real_results(studio):
    await studio.invoke("duck_direct", {"title": "old", "steps": [
        {"action": "walk", "duration": 1}, {"action": "turn_left"}]}, wait=False)
    await asyncio.sleep(.08)
    result = await studio.invoke("duck_direct", {"title": "new", "head_only": True,
        "steps": [{"action": "shake_head", "duration": .2}]})
    assert result["task"]["status"] == "completed"
    records = list(studio.motion.records.values())
    assert not any(r["name"] == "turn_left" for r in records)
    assert next(r for r in records if r["name"] == "walk")["status"] == "cancelled"
    assert result["task"]["results"][0]["name"] == "shake_head"
    assert studio.motion.backend.vx == 0


async def test_external_stop_cancels_entire_plan(studio):
    await studio.invoke("duck_direct", {"title": "cancel", "steps": [
        {"action": "walk", "duration": 1}, {"action": "nod"}]}, wait=False)
    await asyncio.sleep(.04)
    rec = await studio.motion.submit(Action(name="stop"))
    await studio.motion.wait(rec["id"])
    await asyncio.sleep(.1)
    assert studio.state["status"] == "cancelled"
    assert not any(r["name"] == "nod" for r in studio.motion.records.values())


@pytest.mark.parametrize("values", [
    {"head_only": True, "steps": [{"action": "walk"}]},
    {"stationary": True, "steps": [{"action": "turn_left"}]},
    {"steps": [{"action": "nod", "duration": 50}]},
    {"steps": [{"action": "nod"}] * 7},
    {"steps": [{"action": "arbitrary_code"}]},
])
async def test_invalid_plan_does_not_cancel_existing_or_partially_execute(studio, values):
    with pytest.raises(ValidationError):
        await studio.invoke("duck_direct", {"title": "bad", **values})
    assert not studio.motion.records


async def test_failed_step_prevents_later_steps(studio):
    result = await studio.invoke("duck_direct", {"title": "physics required", "steps": [
        {"action": "sit"}, {"action": "nod"}]})
    assert result["task"]["status"] == "failed"
    assert not any(r["name"] == "nod" for r in studio.motion.records.values())


def test_no_unsafe_extra_fields():
    with pytest.raises(ValidationError):
        Routine.model_validate({"title": "bad", "steps": [{"action": "nod", "speed": 20}]})


@pytest.mark.parametrize("pause_after", [.25, 1.4, 2.4])
async def test_real_delivery_resume_keeps_remaining_path(tmp_path, pause_after):
    from duckking.simulation import MuJoCoBackend

    backend = MuJoCoBackend(ASSETS)
    backend.load("carry")
    motion = MotionController(backend)
    studio = Studio(motion, tmp_path)
    motion.studio = studio
    await studio.select("delivery")
    try:
        await studio.invoke("duck_delivery", {"operation": "start"}, wait=False)
        async with asyncio.timeout(8):
            while backend.grasp.phase != "carrying":  # noqa: ASYNC110 - observing physical phase
                await asyncio.sleep(.02)
        await asyncio.sleep(pause_after)
        await studio.invoke("duck_delivery", {"operation": "pause"})
        remaining = backend.grasp.carry_remaining
        assert 0 < remaining < 2.8
        assert backend.grasp.held
        await asyncio.sleep(.35)
        assert backend.grasp.carry_remaining == remaining
        result = await studio.invoke("duck_delivery", {"operation": "resume"})
        # Pytest abbreviates nested dicts, hiding the physical failure reason in CI.
        assert result["task"]["status"] == "completed", json.dumps(
            {"task": result["task"], "grasp": backend.grasp.snapshot(),
             "actions": list(motion.records.values())},
            ensure_ascii=False, indent=2,
        )
        assert backend.grasp.phase == "released"
        assert backend.grasp.released_s >= .2
        assert sum(r["name"] == "pick_up" for r in motion.records.values()) == 1
        assert .10 < backend.grasp.carry_distance < .30
    finally:
        await motion.close()


async def test_real_conductor_replaces_pending_queue(tmp_path):
    from duckking.simulation import MuJoCoBackend

    backend = MuJoCoBackend(ASSETS)
    backend.load("seated")
    motion = MotionController(backend)
    studio = Studio(motion, tmp_path)
    motion.studio = studio
    await studio.select("conductor")
    try:
        await studio.invoke("duck_conduct", {"operation": "start", "order": ["c", "a"]})
        async with asyncio.timeout(12):
            while backend.seated.phase != "solo":
                if studio.task.done():
                    pytest.fail(str(studio.snapshot()))
                await asyncio.sleep(.02)
        assert backend.seated.snapshot()["solo"] == "c"
        await studio.invoke("duck_conduct", {"operation": "queue", "order": ["b"]})
        await asyncio.wait_for(asyncio.shield(studio.task), 30)
        assert studio.state["status"] == "completed", studio.snapshot()
        assert backend.seated.completed_solos == ["c", "b"]
        assert all(p["observed"] == "sit" for p in backend.seated.snapshot()["postures"])
    finally:
        await motion.close()


async def test_recipe_confirmation_versions_and_reload(studio):
    await studio.select("recipe")
    studio.heard("下班就是摇头和点头")
    plan = {"title": "下班", "steps": [{"action": "shake_head", "duration": .2},
                                      {"action": "nod", "duration": .2}]}
    await studio.invoke("duck_recipe", {"operation": "draft", "name": "下班", "plan": plan})
    with pytest.raises(ValueError, match="下一轮"):
        await studio.invoke("duck_recipe", {"operation": "confirm", "name": "下班"})
    studio.heard("确认")
    await studio.invoke("duck_recipe", {"operation": "confirm", "name": "下班"})
    plan["steps"] = [{"action": "nod", "duration": .2}]
    await studio.invoke("duck_recipe", {"operation": "draft", "name": "下班", "plan": plan})
    studio.heard("确认修改")
    await studio.invoke("duck_recipe", {"operation": "confirm", "name": "下班"})
    other_motion = MotionController(PreviewBackend())
    other = Studio(other_motion, studio.data_dir)
    other_motion.studio = other
    await other.select("recipe")
    try:
        result = await other.invoke("duck_recipe", {"operation": "run", "name": "下班"})
        assert result["task"]["recipe_version"] == 2
        assert [r["name"] for r in result["task"]["results"]] == ["nod"]
        await other.invoke("duck_recipe", {"operation": "delete", "name": "下班"})
        with pytest.raises(ValueError):
            await other.invoke("duck_recipe", {"operation": "run", "name": "下班"})
    finally:
        await other_motion.close()


async def test_game_uses_recognized_text_and_blocks_bypass(studio):
    from duckking.mcp import DeviceMCP

    await studio.select("game")
    await studio.invoke("duck_game", {"operation": "configure", "prefix": "鸭王说"})
    command = {"operation": "play", "plan": {"title": "点头", "steps": [
        {"action": "nod", "duration": .2}]}}
    studio.heard("点头")
    assert not (await studio.invoke("duck_game", command))["accepted"]
    assert not studio.motion.records
    mcp = DeviceMCP(studio.motion, "rules")
    response = await mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": "duck_nod"}})
    assert response["result"]["isError"]
    studio.heard("鸭王说，点头")
    assert (await studio.invoke("duck_game", command))["task"]["status"] == "completed"
    await studio.invoke("duck_game", {"operation": "configure", "prefix": "船长说"})
    assert not (await studio.invoke("duck_game", command))["accepted"]
    rec = await studio.motion.submit(Action(name="stop"))
    assert (await studio.motion.wait(rec["id"]))["status"] == "completed"
    await mcp.close()


async def test_discussion_correction_replaces_prior_fact(studio):
    await studio.select("rubber")
    await studio.invoke("duck_discuss", {"fact": "服务端报错", "question": "状态码是多少？"})
    await studio.invoke("duck_discuss", {"fact": "请求没发出", "replace_facts": True,
                                         "question": "点击按钮后控制台有报错吗？"})
    assert studio.snapshot()["discussion"]["facts"] == ["请求没发出"]
    with pytest.raises(ValueError, match="一个追问"):
        await studio.invoke("duck_discuss", {"fact": "请求没发出", "question": "何时？哪里？"})


async def test_timer_extend_old_deadline_does_not_fire_and_cancel(studio):
    # Drive the scheduler with a lightweight backend; actual sit/stand is tested separately.
    calls = []
    async def move(name, **kwargs):
        calls.append(name)
        return {"status": "completed", "name": name}
    studio.move = move
    await studio.select("focus")
    await studio.invoke("duck_focus", {"operation": "start", "seconds": 5})
    await asyncio.sleep(.02)
    studio.helpers.deadline = __import__('time').monotonic() + .08
    studio.helpers.timer_event.set()
    await studio.invoke("duck_focus", {"operation": "extend", "seconds": 5})
    await asyncio.sleep(.14)
    assert "stand" not in calls
    await studio.invoke("duck_focus", {"operation": "cancel"})
    await asyncio.sleep(.1)
    assert "stand" not in calls
    assert studio.helpers.deadline is None


async def test_real_coach_observation_and_kick_never_secretly_reposition(tmp_path):
    import numpy as np

    from duckking.simulation import MuJoCoBackend

    backend = MuJoCoBackend(ASSETS)
    motion = MotionController(backend)
    studio = Studio(motion, tmp_path)
    motion.studio = studio
    await studio.select("coach")
    try:
        before = backend.data.qpos.copy()
        observed = await studio.invoke("duck_coach", {"operation": "observe"})
        assert observed["observation"]["sensor"] == "mujoco_state_query"
        assert np.array_equal(before, backend.data.qpos)
        prepared = await studio.invoke("duck_coach", {"operation": "prepare", "foot": "right"})
        assert prepared["task"]["status"] == "completed", prepared
        wrong = await studio.invoke("duck_coach", {"operation": "kick", "foot": "left"})
        assert wrong["task"]["status"] == "failed"
        assert backend.ball_prepared == "right"
        result = await studio.invoke("duck_coach", {"operation": "kick", "foot": "right"})
        assert result["task"]["status"] == "completed", result
        assert result["task"]["outcome"]["foot"] == "right"
        assert result["task"]["outcome"]["displacement_m"] > .02
        assert backend.ball_prepared is None
    finally:
        await motion.close()


async def test_rejected_confirmation_keeps_draft(studio):
    await studio.select('recipe')
    studio.heard('教一个下班暗号')
    await studio.invoke('duck_recipe', {'operation': 'draft', 'name': '下班',
        'plan': {'title': '下班', 'steps': [{'action': 'nod'}]}})
    studio.heard('不要保存')
    with pytest.raises(ValueError, match='确认'):
        await studio.invoke('duck_recipe', {'operation': 'confirm', 'name': '下班'})
    assert studio.helpers.draft is not None
    assert not studio.helpers.recipes


async def test_voice_interrupt_preserves_waiting_timer_but_disconnect_cancels(studio, tmp_path):
    import time

    from duckking.config import Settings
    from duckking.voice import VoiceSession

    await studio.select('focus')
    started = asyncio.Event()
    async def waiting():
        studio.helpers.deadline = time.monotonic() + 20
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            studio.helpers.deadline = None
    await studio.start('focus', waiting)
    await started.wait()
    async def send(data):
        pass
    session = VoiceSession(send, studio.motion, Settings(data_dir=tmp_path))
    session.pending_input = {'frames': [], 'started': 0.0, 'stopped': False}
    await session._stop_motion()
    assert studio.task and not studio.task.done()
    assert studio.helpers.deadline is not None
    session.pending_input = None
    await session._stop_motion()
    assert studio.helpers.deadline is None
    assert studio.state['status'] == 'cancelled'
