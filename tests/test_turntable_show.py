"""Structural checks for the self-contained turntable show script."""

import ast
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def test_script_parses_and_has_async_flow():
    tree = ast.parse((SCRIPTS / "validate_turntable.py").read_text())
    names = {node.name for node in ast.walk(tree)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert {"main", "build_turntable", "decor", "get_up"} <= names


def test_round_ladder_is_bounded_and_monotonic_inside_the_disk():
    tree = ast.parse((SCRIPTS / "validate_turntable.py").read_text())
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    assert constants["DISK_R"] == pytest.approx(1.02)
    assert max(constants["R0"]) < constants["DISK_R"] - 0.3
    speeds = [speed for speed, *_ in constants["ROUNDS"]]
    assert speeds == sorted(speeds) and all(0.0 < speed <= 6.0 for speed in speeds)


def test_decorations_are_visual_only_markers():
    sys.path.insert(0, str(SCRIPTS))
    from validate_turntable import decor
    xml = decor()
    assert xml.count('contype="0" conaffinity="0"') == xml.count("<geom")
    assert "spoke" in xml and "arrow" in xml and "dot" in xml
