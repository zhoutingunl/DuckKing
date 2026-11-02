"""The three advertised demo goals must not inherit hidden training gates."""

import pytest

from duckking.balance_acceptance import evaluate


def result(level=2, *, done=True, cancelled=False, **changes):
    # Measurements from the reported 18-second seed 8181 round.
    info = dict(seconds=18.0, radius=0.072459788, center_hold=0.1,
                heading_fraction=1.0, disk_stopped=True,
                success=False, reason="criteria_not_met", reward_terms={"fall": -10})
    info.update(changes)
    return evaluate(info, level=level, duration=18, done=done, cancelled=cancelled)


def test_facing_round_passes_without_changing_recorded_training_judgment():
    r = result()
    assert r["success"] and r["reason"] == "success"
    assert r["training_evaluation"]["success"] is False
    assert r["training_evaluation"]["reason"] == "criteria_not_met"
    assert r["reward_terms"] == {"fall": -10}
    assert "center_hold" not in r["acceptance"]["checks"]


def test_goals_only_require_their_advertised_skill():
    assert result(1, radius=0.2, center_hold=0, heading_fraction=0)["success"]
    assert result(2, radius=0.2, center_hold=0, heading_fraction=0.85)["success"]
    assert not result(2, heading_fraction=0.849)["success"]
    assert result(3, center_hold=sum([0.1] * 10), heading_fraction=0)["success"]
    assert not result(3, center_hold=0.9)["success"]
    assert not result(3, center_hold=2, radius=0.08)["success"]


@pytest.mark.parametrize("changes", [
    {"done": False}, {"seconds": 17.9}, {"disk_stopped": False},
    {"reason": "fell_or_left_disc"}, {"reason": "cancelled"}, {"cancelled": True},
    {"seconds": float("nan")}, {"heading_fraction": float("nan")},
])
def test_early_stop_failure_or_invalid_measurements_cannot_be_a_win(changes):
    assert not result(**changes)["success"]
