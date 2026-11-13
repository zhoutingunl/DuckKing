"""Pinned Apache-2.0 acrobatics CPU harness, paced for the browser.

The fixed source judge decides each stage. No reported upstream success rate is
reused. Nominal command delay is 25 ms; all inference and contacts are live.
"""

import ast
import asyncio
import contextlib
import importlib
import io
import math
import sys
import time
import types
from collections import defaultdict
from pathlib import Path

import mujoco
import numpy as np
import onnxruntime as ort

from .feature_bam import compile_bam
from .feature_policies import PolicyWorld, module
from .feature_source import source_symbols
from .model_assets import geometry


class CheckedPolicy:
    def __init__(self, policy):
        self.policy = policy
        self.action_scale = policy.action_scale

    def __call__(self, obs):
        action = self.policy(obs)
        if action.shape != (14,) or not np.isfinite(action).all():
            raise ValueError("策略输出无效，已暂停物理")
        return action


class AcrobaticsWorld(PolicyWorld):
    def __init__(self, assets):
        self.capability = "acrobatics"
        self.root = assets / "features"
        source = self.root / "acrobatics/bench/duckbench"
        ip = module(self.root / "upstream/scripts/infer_policy.py", "feature_acrobatics_ip")

        def compile_scene(xml, motor, timestep, vin_drop_gain, vin_min):
            result = compile_bam(
                mujoco.MjSpec.from_file(str(xml)), motor, timestep=timestep, vin_min=vin_min
            )
            result[2].vin_drop_gain = vin_drop_gain
            return result

        ip.load_mujoco_with_bam = compile_scene
        name = "feature_acrobench"
        package = types.ModuleType(name)
        package.__path__ = [str(source)]
        sys.modules[name] = package
        path = source / "sim.py"
        # Exclude import-time environment/path mutations and the configurable
        # REPO expression. Only pinned definitions and constants are loaded.
        names = set()
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                names.update(
                    t.id
                    for t in node.targets
                    if isinstance(t, ast.Name) and t.id.isupper() and t.id != "REPO"
                )
        ns = source_symbols(
            path,
            names,
            dict(
                __name__=name + ".sim",
                REPO=self.root / "upstream",
                ip=ip,
                contextlib=contextlib,
                io=io,
                math=math,
                os=None,
                sys=sys,
                Path=Path,
                np=np,
                mujoco=mujoco,
                ort=ort,
            ),
        )
        simmod = types.ModuleType(name + ".sim")
        simmod.__dict__.update(ns)
        sys.modules[name + ".sim"] = simmod
        for sub in ["routine", "scenarios"]:
            sys.modules.pop(name + "." + sub, None)
        self.routine = importlib.import_module(name + ".routine")
        self.sim = ns["DuckSim"](delay_steps=5)
        self.model, self.data = self.sim.model, self.sim.data
        self.body = self.sim.trunk
        self.pol = types.SimpleNamespace(_trunk_qpos_adr=self.sim.free_q)
        self.geom_ids = [i for i in range(self.model.ngeom) if self.model.geom_group[i] == 2]
        self.visual = geometry(self.model, self.geom_ids)
        self.policies = {
            "walk": ns["Policy"](assets / "policies/velstand.onnx"),
            "stand": ns["Policy"](self.root / "policies/circus-base/alpha_stand.onnx"),
            "backroll": ns["Policy"](self.root / "acrobatics/policies/backroll_robust.onnx"),
            "headstand": ns["Policy"](self.root / "acrobatics/policies/headspin_robust.onnx"),
            "hold": ns["ZeroPolicy"](),
        }
        self.policies = {name: CheckedPolicy(policy) for name, policy in self.policies.items()}
        self.command = np.zeros(13, np.float32)
        self.reset_state()

    def reset_state(self):
        mujoco.mj_resetData(self.model, self.data)
        self.sim.reset()
        self.metrics = {}
        self.trial_started = False
        self.phase = "ready"

    async def perform(self, command):
        if self.trial_started:
            raise ValueError("本轮已结束；再次点击动作会自动重置起点。")
        self.trial_started = True
        r = self.routine
        stages = r.build_routine(headstand_s=3, spins=((4, 4), (-4, 4)))
        if command.action == "backroll":
            stages = stages[1:4]
        elif command.action == "headstand":
            stages = [stages[4], *stages[-2:]]
        elif command.action in {"spin_left", "spin_right"}:
            spin = stages[5 if command.action == "spin_left" else 6]
            stages = [stages[4], spin, *stages[-3:]]
        trace = defaultdict(list)
        starts = {}
        deadline = time.monotonic()
        for index, stage in enumerate(stages):
            self.phase = stage.name
            starts[stage.name] = len(trace["t"])
            for _ in range(round(stage.seconds / 0.02)):
                before = self.data.time
                self.sim.step(self.policies[stage.role], stage.cmd())
                if self.data.time <= before or not np.isfinite(self.data.qpos).all():
                    raise ValueError("物理数值异常，已暂停；请重新准备场景。")
                state = self.sim.state()
                for key, value in state.items():
                    trace[key].append(value)
                self.metrics.update(
                    stages_completed=index,
                    sim_time=float(self.data.time),
                    head_support=float(state["on_head"]),
                )
                deadline += 0.02
                await asyncio.sleep(max(0.001, deadline - time.monotonic()))
            if stage.check:
                passed, info = stage.check({k: np.asarray(v) for k, v in trace.items()}, starts)
                for key in ["roll_deg", "on_head_fraction", "ratio", "deg_s"]:
                    if isinstance(info.get(key), (int, float, np.number)):
                        self.metrics[key] = float(info[key])
                if not passed:
                    return dict(
                        verified=False,
                        message="本阶段未通过验收，连续技已暂停",
                        failed_stage=stage.name,
                        **self.metrics,
                    )
            self.metrics["stages_completed"] = index + 1
        return dict(verified=True, message="所选连续技已通过分段验收", **self.metrics)

    async def reset(self):
        self.reset_state()

    async def snapshot(self):
        state = await super().snapshot()
        on_head = self.sim.state()["on_head"]
        if on_head:
            state["ducks"][0]["fallen"] = False
        state["camera_follow"] = state["ducks"][0]["position"]
        phases = {
            "ready": "等待指令",
            "walk": "向前走",
            "stop": "站定",
            "roll": "后滚翻",
            "recover": "恢复站立",
            "headstand": "倒立",
            "spin1": "向左头旋",
            "spin2": "向右头旋",
            "spin_stop": "停止头旋",
            "release": "放下身体",
            "standup": "恢复站立",
        }
        state["annotations"] = [
            dict(
                id="acro_phase",
                text=phases[self.phase],
                position=[*state["ducks"][0]["position"][:2], 0.38],
            )
        ]
        return state
