import runpy

import pytest

physics_state = runpy.run_path("scripts/benchmark_physics.py")["physics_state"]


def test_probe_reads_physics_inside_motion_controller_envelope():
    frame = {
        "type": "state",
        "backend": {"kind": "mujoco", "sim_time": 12.3},
        "events": [],
        "action": None,
    }
    assert physics_state(frame)["sim_time"] == 12.3


@pytest.mark.parametrize(
    "frame",
    [
        {"type": "not_started"},
        {"type": "state", "backend": {"kind": "preview"}},
        {"type": "state", "backend": "mujoco"},
    ],
)
def test_probe_rejects_missing_physics_clock_instead_of_reporting_zero_speed(frame):
    with pytest.raises(ValueError, match="Missing actual physics time"):
        physics_state(frame)


@pytest.mark.parametrize("status", ["failed", "CancelledError", "HTTPStatusError", "TimeoutError"])
def test_probe_never_passes_an_action_failure_even_when_frames_are_fast(status):
    stage_passed = runpy.run_path("scripts/benchmark_physics.py")["stage_passed"]
    readings = [{"active_rtf": 1.0, "frame_gap_ms": {"p95": 50}, "error": None}]
    health = {"health_errors": 0, "health_ms": {"p95": 10}}
    assert not stage_passed(1, readings, [{"status": status}], health)
