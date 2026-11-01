"""Live balance room: the training physics and exported task PPO, no torch server."""

import asyncio
import time

import numpy as np

from .balance import DT, LEVELS, BalanceConfig, BalanceWorld
from .balance_policy import BalancePolicy
from .model_assets import geometry

BALANCE_TOOLS = [
    {
        "name": "duck_balance",
        "description": (
            "语音平衡教练：start 开始一关；stop 平滑减速并保持控制至停稳；status 读取真实结果。"
            "level 1 随盘站稳、2 保持面向观众、3 从偏心位置回中心。"
            "controller trained 是已训练任务 PPO＋官方步态；early 是训练步数0的任务网络＋官方步态；"
            "baseline 只有官方步态。无策略时报错，不能声称现场一句话就学会了。"
            "默认与左侧官方基线同步对照：同种子、同目标节奏、独立物理受力；"
            "一侧结束后定格，另一侧继续。comparison.baseline 是左侧成绩，外层是右侧成绩。"
            "成功须完成10秒扰动及3秒减速。只能根据返回的数据报告成绩。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["start", "stop", "status"]},
                "level": {"type": "integer", "minimum": 1, "maximum": 3},
                "controller": {"type": "string", "enum": ["trained", "early", "baseline"]},
                "seed": {"type": "integer", "minimum": 0, "maximum": 9999},
                "compare": {"type": "boolean", "description": "与官方基线同步对照，默认开启"},
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
    }
]


class BalanceBackend:
    kind, scene, default_speed = "mujoco", "balance", 0.18

    def __init__(self, assets, runs):
        self.world = BalanceWorld(assets)
        # The pair resets to the SAME seed under one lock and steps serially.
        # Share compiled geometry/session, never MjData or gait history. Reset's
        # only model mutation (surface friction) is identical on both sides.
        self.baseline = BalanceWorld(
            assets,
            compiled=(self.world.model, self.world.fingerprint),
            session=self.world.session,
        )
        self.runs = runs
        self.revision = "balance-" + self.world.fingerprint[:24]
        self.geom_ids = [
            i
            for i in range(self.world.model.ngeom)
            if self.world.model.geom_group[i] == 2
            or self.world.model.geom(i).name.startswith("disc_")
            or self.world.model.geom_bodyid[i] == (self.world.model.body("balance_base").id)
        ]
        self.visual = {"revision": self.revision, **geometry(self.world.model, self.geom_ids)}
        self.lock = asyncio.Lock()
        self.commands = asyncio.Lock()
        self.generation = 0
        self.request_version = 0
        self.task = None
        self.policy = None
        self.controller = "baseline"
        self.run_id = None
        self.error = None
        self.phase = "idle"
        self.info = None
        self.started = time.monotonic()
        self.finished_wall = None
        self.compare = True
        self.baseline_info = self.baseline_error = None
        self.baseline_phase = self.comparison_phase = "idle"
        self.comparison_ticks = 0

    def geometry(self):
        return self.visual

    async def prepare(self, action):
        if action.name not in {"stop", "reset"}:
            raise ValueError("圆盘上请使用平衡教练工具，不能叠加普通动作")

    async def reset(self):
        await self.stop()
        async with self.lock:
            self.world.reset(self.world.seed)
            self.baseline.config = self.world.config
            self.baseline.reset(self.world.seed)
            self.info, self.error, self.phase = None, None, "idle"
            self.baseline_info = self.baseline_error = None
            self.baseline_phase = self.comparison_phase = "idle"
            self.comparison_ticks = 0

    async def invoke(self, args):
        if not isinstance(args, dict) or set(args) - {
            "operation",
            "level",
            "controller",
            "seed",
            "run",
            "compare",
        }:
            raise ValueError("不支持的平衡教练参数")
        if not isinstance(args.get("operation"), str):
            raise ValueError("平衡教练操作必须为字符串")
        if args.get("operation") == "status":
            async with self.lock:
                return self.summary()
        if args.get("operation") == "stop":
            await self.stop()
            return self.summary()
        if self.commands.locked():
            raise ValueError("上一条场景切换仍在停盘，请稍后重试")
        async with self.commands:
            self.request_version += 1
            return await self._invoke(args, self.request_version)

    async def _invoke(self, args, version):
        if set(args) - {"operation", "level", "controller", "seed", "run", "compare"}:
            raise ValueError("不支持的平衡教练参数")
        operation = args.get("operation")
        if operation == "status":
            return self.summary()
        if operation == "stop":
            await self.stop()
            return self.summary()
        if operation not in {"start", "select"}:
            raise ValueError("未知平衡教练操作")
        level = args.get("level", self.world.config.level)
        seed = args.get("seed", 0)
        controller = args.get("controller", "trained")
        compare = args.get("compare", True)
        if (
            type(level) is not int
            or level not in LEVELS
            or type(seed) is not int
            or not 0 <= seed <= 9999
            or not isinstance(controller, str)
            or controller not in {"baseline", "early", "trained"}
            or type(compare) is not bool
        ):
            raise ValueError("无效关卡、策略或测试种子")
        # Validate requested policy before replacing or cancelling a live challenge.
        manifest = {**self.world.manifest(), "config": {"level": level}}
        policy, run = None, None
        if operation == "start" and controller != "baseline":
            path, run = self.runs.policy(level, args.get("run"), controller, manifest["contract"])
            policy = BalancePolicy(path, manifest)
        await self._halt()
        if version != self.request_version:
            raise ValueError("该挑战已被新的停止指令取消")
        self.generation += 1
        generation = self.generation
        async with self.lock:
            self.world.config = BalanceConfig(level=level)
            self.world.reset(seed)
            self.baseline.config = self.world.config
            self.baseline.reset(seed)
            self.compare = compare
            self.comparison_ticks = 0
            self.baseline_info = self.baseline_error = None
            self.baseline_phase = "running" if compare and operation == "start" else "idle"
            self.comparison_phase = "running" if operation == "start" else "idle"
            self.policy, self.controller, self.run_id = (
                policy,
                controller if operation == "start" else "baseline",
                run,
            )
            self.info, self.error, self.phase = None, None, "running"
            self.started = time.monotonic()
            self.finished_wall = None
            if operation == "start":
                self.task = asyncio.create_task(self._loop(generation))
            else:
                self.phase = "idle"
        return self.summary()

    async def _loop(self, generation):
        try:
            while generation == self.generation and (
                not self.world.done or (self.compare and not self.baseline.done)
            ):
                began = time.monotonic()
                async with self.lock:
                    # Publish only after BOTH worlds have advanced this tick.
                    # Wall-clock overload slows the pair together, not one side.
                    await asyncio.to_thread(self._advance_pair)
                    self.comparison_ticks += 1
                await asyncio.sleep(max(0, DT - (time.monotonic() - began)))
            self.comparison_phase = (
                "cancelled"
                if self.world.stop_at is not None
                or (self.compare and self.baseline.stop_at is not None)
                else "completed"
            )
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.comparison_phase = "failed"
            if self.phase in {"running", "stopping"}:
                self.phase = "failed"
            if self.compare and self.baseline_phase in {"running", "stopping"}:
                self.baseline_phase = "failed"
                self.baseline_error = "对照计算异常，两侧物理已暂停"
            # Explicit physical pause on invalid inference/physics, never scripted recovery.
        finally:
            self.finished_wall = time.monotonic()

    @staticmethod
    def _terminal_phase(world, info):
        return (
            "completed"
            if info["success"]
            else "cancelled"
            if world.stop_at is not None
            else "failed"
        )

    def _advance_pair(self):
        if not self.world.done:
            action = self.policy(self.world.observation()) if self.policy else np.zeros(3)
            _, _, _, _, self.info = self.world.step(action)
            if self.world.done:
                self.phase = self._terminal_phase(self.world, self.info)
        if self.compare and not self.baseline.done:
            _, _, _, _, self.baseline_info = self.baseline.step(np.zeros(3))
            if self.baseline.done:
                self.baseline_phase = self._terminal_phase(self.baseline, self.baseline_info)

    async def stop(self):
        self.request_version += 1
        await self._halt()

    async def _halt(self):
        if self.task and not self.task.done():
            async with self.lock:
                if not self.world.done:
                    self.world.request_stop()
                    self.phase = "stopping"
                if self.compare and not self.baseline.done:
                    self.baseline.request_stop()
                    self.baseline_phase = "stopping"
                self.comparison_phase = "stopping"
            await asyncio.shield(self.task)

    def summary(self):
        result = self._summary(self.world, self.info, self.phase, self.error, self.controller)
        result["run"] = self.run_id
        result["policy_steps"] = getattr(self.policy, "steps", None)
        result["comparison"] = {
            "enabled": self.compare,
            "phase": self.comparison_phase,
            "execution": "running"
            if self.comparison_phase in {"running", "stopping"}
            else "paused",
            "clock": "shared_task_ticks",
            "tick": self.comparison_ticks,
            "sim_time": round(self.comparison_ticks * DT, 6),
            "disturbance": "same_seed_and_motor_targets; independent_contact_dynamics",
            "terminal_behavior": "freeze_finished_side",
            "baseline": self._summary(
                self.baseline,
                self.baseline_info,
                self.baseline_phase,
                self.baseline_error,
                "baseline",
            ),
        }
        result["operation_failed"] |= self.comparison_phase == "failed"
        return result

    @staticmethod
    def _summary(world, info, phase, error, controller):
        return {
            "level": world.config.level,
            "title": LEVELS[world.config.level]["title"],
            "phase": phase,
            "controller": controller,
            "seed": world.seed,
            "result": info,
            "error": error,
            "sim_time": float(world.data.time),
            "operation_failed": phase == "failed",
            "source": "MuJoCo; PPO feedback-gain inference + official gait"
            if controller != "baseline"
            else "MuJoCo; frozen official gait baseline, no task PPO",
            "execution": "running" if phase in {"running", "stopping"} else "paused",
        }

    async def snapshot(self):
        async with self.lock:
            summary = self.summary()
            frame = self._frame(self.world, summary)
            frame["comparison"] = {
                "baseline": self._frame(self.baseline, summary["comparison"]["baseline"])
            }
            return frame

    def _frame(self, world, summary):
        d = world.data
        pos, yaw = world.driver.pose(d)
        return {
            "kind": self.kind,
            "scene": self.scene,
            "connected": summary["error"] is None,
            "physics": True,
            "revision": self.revision,
            "error": summary["error"],
            "balance": summary,
            "pose": {},
            "velocity": {"forward": 0},
            "ball": None,
            "grasp": None,
            "stage": None,
            "tabletop": None,
            "seated_choir": None,
            "idle": None,
            "skill": None,
            "contacts": {},
            "discovered": [],
            "chorus": None,
            "observation": world.observation().tolist(),
            "task_action": world.command.tolist(),
            "sim_time": float(d.time),
            "real_time_factor": float(d.time)
            / max(0.001, (self.finished_wall or time.monotonic()) - self.started),
            "ducks": [{"id": "a", "position": pos.tolist(), "yaw": yaw}],
            "disc_target": world.target.tolist(),
            "geoms": [
                {
                    "id": i,
                    "position": d.geom_xpos[i].tolist(),
                    "rotation": d.geom_xmat[i].tolist(),
                }
                for i in self.geom_ids
            ],
        }

    async def close(self):
        await self.stop()
        self.generation += 1
