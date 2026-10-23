import asyncio
import math
from dataclasses import asdict

import pytest
from pydantic import ValidationError

from duckking.choreography import CHOREOGRAPHIES, sample
from duckking.motion import Action, MotionController, PreviewBackend


@pytest.mark.parametrize("name", CHOREOGRAPHIES)
@pytest.mark.parametrize("duration", [2.4, 3.0])
def test_all_frames_stay_bounded_and_finish_neutral(name, duration):
    for i in range(601):
        frame = sample(name, duration * i / 600, duration)
        assert all(math.isfinite(v) for k, v in asdict(frame).items() if k != "phase")
        assert abs(frame.forward) <= 0.4 and abs(frame.lateral) <= 0.3 and abs(frame.turn) <= 0.6
        assert -0.025 <= frame.body_z <= 0.01
        assert abs(frame.body_roll) <= 0.26 and abs(frame.body_pitch) <= 0.26
        assert abs(frame.head_yaw) <= 0.25 and abs(frame.head_roll) <= 0.1
        assert not frame.body_active or (frame.forward, frame.lateral, frame.turn) == (0, 0, 0)
    assert all(
        value == 0
        for key, value in asdict(sample(name, duration + 1, duration)).items()
        if key != "phase"
    )
    assert sample(name, -1, duration) == sample(name, 0, duration)


def test_flash_has_opposite_lateral_beats_and_bear_stays_planted():
    flash = [sample("flash_step", i / 100) for i in range(301)]
    bear = [sample("bear_shake", i / 100) for i in range(301)]
    assert list(dict.fromkeys(f.phase for f in flash)) == ["预备", "左闪", "回闪", "收势"]
    assert max(f.lateral for f in flash) > 0.25 and min(f.lateral for f in flash) < -0.25
    assert all((f.forward, f.lateral, f.turn) == (0, 0, 0) for f in bear)
    assert max(f.body_roll for f in bear) > 0.06 and min(f.body_roll for f in bear) < -0.06
    assert min(f.body_z for f in bear) < -0.01
    assert all(f.body_roll * f.head_roll <= 0 for f in bear)


@pytest.mark.parametrize(
    "name,boundaries", [("flash_step", [0.12, 0.42, 0.76]), ("bear_shake", [0.16, 0.84])]
)
def test_segment_boundaries_are_continuous(name, boundaries):
    for u in boundaries:
        before, after = (
            asdict(sample(name, 3 * u - 0.000001)),
            asdict(sample(name, 3 * u + 0.000001)),
        )
        for key in before.keys() - {"phase", "body_active"}:
            assert abs(before[key] - after[key]) < 0.0001


@pytest.mark.parametrize(
    "name,elapsed,duration",
    [
        ("unknown", 0, 3),
        ("flash_step", float("nan"), 3),
        ("bear_shake", 0, float("inf")),
        ("bear_shake", 0, 0.2),
        ("bear_shake", 0, 4),
    ],
)
def test_invalid_timing_cannot_accelerate_gesture(name, elapsed, duration):
    with pytest.raises(ValueError):
        sample(name, elapsed, duration)


@pytest.mark.parametrize("name", CHOREOGRAPHIES)
def test_named_gestures_have_their_own_default_and_minimum_duration(name):
    assert Action(name=name).duration == 3
    assert Action(name=name, duration=2.4).duration == 2.4
    with pytest.raises(ValidationError):
        Action(name=name, duration=1.2)
    with pytest.raises(ValidationError):
        Action(name=name, speed=0.2)
    assert Action(name="nod").duration == 1.2


async def test_bear_runs_all_phases_and_restores_every_pose_axis():
    controller = MotionController(PreviewBackend())
    await controller.submit(Action(name="bear_shake", duration=2.4, request_id="bear"))
    result = await controller.wait("bear")
    assert result["status"] == "completed"
    assert [event["text"] for event in controller.events if event["kind"] == "phase"] == [
        "狗熊哆嗦毛 · 轻蹲",
        "狗熊哆嗦毛 · 抖毛",
        "狗熊哆嗦毛 · 收势",
    ]
    snapshot = await controller.backend.snapshot()
    assert all(value == 0 for value in snapshot["pose"].values())
    assert all(value == 0 for value in snapshot["velocity"].values())


async def test_stop_cancels_flash_mid_step_without_resuming_or_leaving_body_tilt():
    stepped = asyncio.Event()

    class Observed(PreviewBackend):
        async def move(self, vx, vyaw, vy=0):
            await super().move(vx, vyaw, vy)
            if abs(vy) > 0.1:
                stepped.set()

    controller = MotionController(Observed())
    await controller.submit(Action(name="flash_step", request_id="flash"))
    await asyncio.wait_for(stepped.wait(), 2)
    await controller.submit(Action(name="stop", request_id="stop"))
    assert (await controller.wait("flash"))["status"] == "cancelled"
    await controller.wait("stop")
    position = (await controller.backend.snapshot())["pose"]
    await asyncio.sleep(0.1)
    assert (await controller.backend.snapshot())["pose"] == position
    assert all(
        position[k] == 0 for k in ["body_z", "body_roll", "body_pitch", "head_yaw", "head_roll"]
    )


async def test_mid_frame_failure_does_not_leave_crouch_active():
    class Broken(PreviewBackend):
        async def head(self, *args):
            raise OSError("head transport lost")

    controller = MotionController(Broken())
    await controller.submit(Action(name="bear_shake", request_id="fail"))
    assert (await controller.wait("fail"))["status"] == "failed"
    assert (await controller.backend.snapshot())["pose"]["body_z"] == 0
