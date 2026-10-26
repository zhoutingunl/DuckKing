"""Light structural checks for the scene-show validation scripts."""

import ast
import inspect
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    return ast.parse((SCRIPTS / name).read_text(), filename=name)


def test_show_scripts_parse_and_live_under_scripts():
    for name in ("validate_teletubbies.py", "validate_turntable.py",
                 "validate_marathon.py", "racekit.py"):
        tree = load(name)
        assert any(isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef)
                   for node in tree.body), name


def test_turntable_rounds_and_radii_stay_inside_the_disk():
    tree = load("validate_turntable.py")
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    assert constants["DISK_R"] == pytest.approx(1.02)
    assert max(constants["R0"]) < constants["DISK_R"] - 0.3
    for speed, _hold, _sit in constants["ROUNDS"]:
        assert 0.0 < speed <= 6.0  # bounded ladder only
    assert [speed for speed, *_ in constants["ROUNDS"]] == sorted(
        speed for speed, *_ in constants["ROUNDS"])


def test_turntable_decorations_are_visual_only_and_include_markers():
    import sys

    sys.path.insert(0, str(SCRIPTS))
    from validate_turntable import decor
    xml = decor()
    assert xml.count('contype="0" conaffinity="0"') == xml.count("<geom")
    assert "spoke" in xml and "arrow" in xml and "dot" in xml


def test_racekit_walk_to_signature_is_bounded():
    import sys

    sys.path.insert(0, str(SCRIPTS))
    from racekit import walk_to
    assert inspect.iscoroutinefunction(walk_to)
    parameters = inspect.signature(walk_to).parameters
    assert "give_s" in parameters and "timeout" not in parameters
    assert parameters["near"].default == pytest.approx(0.12)
