"""Bounded paired seesaw execution shared by local controls and Linx MCP."""

import asyncio
import json
import time
from pathlib import Path

from .model_assets import geometry
from .seesaw import DT, DURATION, SeesawWorld
from .seesaw_policy import SeesawPolicy

SEESAW_TOOLS = [
    {
        "name": "duck_seesaw",
        "description": (
            "语音跷跷板教练。板面没有电机，鸭子的走动通过接触改变板面倾角。"
            "start 重新开始12秒左右对照；controller trained 是已训练PPO。"
            "early 是本轮训练开始时的PPO，可能继承前一阶段任务策略。"
            "rule 是明确的人工规则，baseline 是官方步态站定。两侧同初态但独立受力，"
            "板角不会被强制同步。"
            "nudge 手动探索只指挥右侧，左侧保持站定并推进物理："
            "direction forward 向绿色前端走、backward 向赭色后端退、"
            "hold 站定观察，seconds 整数1至3秒，默认2秒；保持当前物理状态，不重置。"
            "reset 重置两侧；stop 停止任务并暂停两侧仿真，不能声称已自然停稳；status 读取真实测量。"
            "正倾角为绿色前端下沉；position_m 是鸭子相对支点的前后位置，正为绿色前端。"
            "开始返回只表示受理；只有phase success才成功；failed是失败，explored是手动探索结束"
            "不计分。"
            "请用status读取最终结果，不要根据发出的步速推断已走动。观察来自MuJoCo真值，不是摄像头。"
            "例如‘用训练后的策略保持平衡’调用start trained；‘向前一点，看看板会怎样’"
            "调用nudge forward。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["start", "stop", "status", "reset", "nudge"],
                },
                "controller": {"type": "string", "enum": ["trained", "early", "baseline", "rule"]},
                "seed": {"type": "integer", "minimum": 0, "maximum": 9999},
                "direction": {"type": "string", "enum": ["forward", "backward", "hold"]},
                "seconds": {"type": "integer", "minimum": 1, "maximum": 3},
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
    }
]


class SeesawArtifacts:
    def __init__(self, directory):
        self.directory = Path(directory)

    def report(self):
        try:
            report = json.loads((self.directory / "report.json").read_text())
            return report if isinstance(report, dict) else None
        except (OSError, ValueError):
            return None

    def policy(self, which, manifest):
        report = self.report()
        if (
            not report
            or report.get("phase") != "completed"
            or not isinstance(report.get("manifest"), dict)
            or not isinstance(report.get("test"), dict)
            or not report["test"].get("episodes")
            or report.get("manifest", {}).get("model_sha256") != manifest["model_sha256"]
        ):
            raise ValueError("尚无与当前物理模型匹配的已评估策略，可选择规则控制或手动探索")
        return SeesawPolicy(
            self.directory / ("early.json" if which == "early" else "policy.json"), manifest
        )


class SeesawBackend:
    kind, scene, default_speed = "mujoco", "seesaw", 0.25

    def __init__(self, assets, artifacts):
        self.world = SeesawWorld(assets)
        self.baseline = SeesawWorld(
            assets, compiled=(self.world.model, self.world.fingerprint), session=self.world.session
        )
        self.artifacts = artifacts
        self.revision = "seesaw-" + self.world.fingerprint[:24]
        self.geom_ids = [
            g
            for g in range(self.world.model.ngeom)
            if self.world.model.geom_group[g] == 2
            or self.world.model.geom(g).name.startswith("seesaw_")
            and self.world.model.geom(g).name != "seesaw_floor"
        ]
        self.visual = {"revision": self.revision, **geometry(self.world.model, self.geom_ids)}
        self.lock, self.commands = asyncio.Lock(), asyncio.Lock()
        self.task, self.policy = None, None
        self.closed = self.stopping = False
        self.phase = self.baseline_phase = "idle"
        self.controller, self.mode = "baseline", "compare"
        self.info = self.baseline_info = self.error = None
        self.revision_number = 0
        self.request_version = 0
        self.trace = []

    def geometry(self):
        return self.visual

    async def prepare(self, action):
        if action.name not in {"stop", "reset"}:
            raise ValueError("跷跷板上请使用教练工具，不能叠加普通动作")

    async def reset(self):
        await self.invoke({"operation": "reset"})

    @staticmethod
    def validate(args):
        if not isinstance(args, dict):
            raise ValueError("无效跷跷板参数")
        op = args.get("operation")
        fields = {
            "start": {"controller", "seed"},
            "reset": {"seed"},
            "nudge": {"direction", "seconds"},
            "status": set(),
            "stop": set(),
        }
        if not isinstance(op, str) or op not in fields or set(args) - fields[op] - {"operation"}:
            raise ValueError("未知跷跷板操作或不适用参数")
        for key, low, high in (("seed", 0, 9999), ("seconds", 1, 3)):
            if key in args and (type(args[key]) is not int or not low <= args[key] <= high):
                raise ValueError("种子必须为0–9999的整数，手动步长必须为1–3秒整数")
        if "controller" in args and args["controller"] not in (
            "trained",
            "early",
            "rule",
            "baseline",
        ):
            raise ValueError("未知任务控制器")
        if op == "nudge" and args.get("direction") not in ("forward", "backward", "hold"):
            raise ValueError("请选择前进、后退或站定")
        return op

    async def invoke(self, args):
        op = self.validate(args)
        if op == "status":
            async with self.lock:
                return self.summary()
        if op == "stop":
            await self.stop()
            return self.summary()
        if self.commands.locked():
            raise ValueError("上一条任务正在切换，请稍后重试")
        async with self.commands:
            if self.closed:
                raise ValueError("场景已关闭，请重新准备")
            controller = args.get("controller", "trained")
            # Reject unavailable/incompatible policies BEFORE altering the current task.
            policy = (
                self.artifacts.policy(controller, self.world.manifest())
                if (op == "start" and controller in {"trained", "early"})
                else None
            )
            self.request_version += 1
            version = self.request_version
            await self._halt()
            async with self.lock:
                if self.closed or version != self.request_version:
                    raise ValueError("本次请求已被停止或场景关闭取消")
                if op in {"start", "reset"}:
                    seed = args.get("seed", self.world.seed)
                    self.world.reset(seed)
                    self.baseline.reset(seed)
                    self.info = self.baseline_info = self.error = None
                    self.phase = self.baseline_phase = "idle"
                    self.trace = []
                    self.mode = "compare"
                elif self.world.done or self.error:
                    raise ValueError("本轮已结束，请先重置跷跷板")
                self.revision_number += 1
                if op != "reset":
                    self.controller = controller if op == "start" else "manual"
                    self.mode = "compare" if op == "start" else "explore"
                    self.policy = policy
                    self.phase = "running"
                    if not self.baseline.done:
                        self.baseline_phase = "running"
                    self.stopping = False
                    self.task = asyncio.create_task(
                        self._loop(
                            int(args.get("seconds", 2) / DT)
                            if op == "nudge"
                            else int(DURATION / DT),
                            {"hold": 0, "forward": 1, "backward": 2}.get(args.get("direction"), 0),
                        )
                    )
            return self.summary()

    def _tick(self, manual_action):
        if not self.world.done:
            obs = self.world.observation()
            action = (
                manual_action
                if self.mode == "explore"
                else self.policy(obs)
                if self.policy
                else SeesawWorld.rule_action(obs)
                if self.controller == "rule"
                else 0
            )
            _, _, _, _, self.info = self.world.step(action)
            if self.world.done:
                self.phase = "success" if self.info["success"] else "failed"
                if self.mode == "explore" and self.info["reason"] != "fell_or_left_board":
                    self.phase = "explored"
                    self.info.update(success=False, reason="exploration_limit")
        if not self.baseline.done:
            _, _, _, _, self.baseline_info = self.baseline.step(0)
            if self.baseline.done:
                self.baseline_phase = "success" if self.baseline_info["success"] else "failed"
                if self.mode == "explore" and self.baseline_info["reason"] != "fell_or_left_board":
                    self.baseline_phase = "explored"
                    self.baseline_info.update(success=False, reason="exploration_limit")
        self.trace.append(
            {
                "seconds": max(float(self.world.data.time), float(self.baseline.data.time)),
                "position_cm": self.info["position_m"] * 100,
                "angle_deg": self.info["angle_deg"],
                "velocity_cm_s": float(self.world.command[0]) * 100,
                "contact_torque_nm": self.info["contact_torque_nm"],
                "baseline_angle_deg": self.baseline.measure()["angle_deg"],
            }
        )
        self.trace = self.trace[-120:]

    async def _loop(self, ticks, manual_action):
        try:
            for _ in range(ticks):
                began = time.monotonic()
                async with self.lock:
                    if self.stopping or self.closed:
                        break
                    await asyncio.to_thread(self._tick, manual_action)
                    if self.world.done and self.baseline.done:
                        break
                await asyncio.sleep(max(0, DT - (time.monotonic() - began)))
            async with self.lock:
                if self.phase == "running":
                    self.phase = "cancelled" if self.stopping else "explored"
                if self.baseline_phase == "running":
                    self.baseline_phase = "cancelled" if self.stopping else "explored"
                # Stopping is an explicitly labelled simulation pause. No claims
                # that a passive physical board has magically come to rest.
                self.world.command[:] = self.world.driver.command[:] = 0
                self.baseline.command[:] = self.baseline.driver.command[:] = 0
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.phase = "failed"
            self.world.command[:] = self.world.driver.command[:] = 0
            self.baseline.command[:] = self.baseline.driver.command[:] = 0
            if self.baseline_phase == "running":
                self.baseline_phase = "failed"

    async def _halt(self):
        self.stopping = True
        if self.task and not self.task.done():
            await asyncio.shield(self.task)

    async def stop(self):
        self.request_version += 1
        await self._halt()

    async def close(self):
        self.closed = True
        self.request_version += 1
        await self._halt()

    def _summary(self, world, phase, info, controller):
        return {
            "phase": phase,
            "controller": controller,
            "seed": world.seed,
            "start_x_m": world.start_x,
            "friction": world.friction,
            "sim_time": float(world.data.time),
            "duration_seconds": DURATION,
            "measurement": world.measure(),
            "result": info,
            "action": world.last_action,
            "command_m_s": float(world.command[0]),
            "execution": "running" if phase == "running" else "paused",
        }

    def summary(self):
        return {
            **self._summary(self.world, self.phase, self.info, self.controller),
            "mode": self.mode,
            "error": self.error,
            "operation_failed": self.phase == "failed",
            "policy_steps": getattr(self.policy, "steps", None),
            "command_revision": self.revision_number,
            "trace": self.trace.copy(),
            "source": "MuJoCo passive hinge + frozen official gait",
            "comparison": self._summary(
                self.baseline, self.baseline_phase, self.baseline_info, "baseline"
            ),
        }

    def _frame(self, world, summary):
        pos, yaw = world.driver.pose(world.data)
        return {
            "kind": self.kind,
            "scene": self.scene,
            "physics": True,
            "connected": self.error is None,
            "error": self.error,
            "revision": self.revision,
            "seesaw": summary,
            "pose": {},
            "velocity": {"forward": float(world.command[0])},
            "sim_time": float(world.data.time),
            "ducks": [{"id": "a", "position": pos.tolist(), "yaw": yaw}],
            "observation": world.observation().tolist(),
            "geoms": [
                {
                    "id": g,
                    "position": world.data.geom_xpos[g].tolist(),
                    "rotation": world.data.geom_xmat[g].tolist(),
                }
                for g in self.geom_ids
            ],
        }

    async def snapshot(self):
        async with self.lock:
            summary = self.summary()
            result = self._frame(self.world, summary)
            result["comparison"] = {"baseline": self._frame(self.baseline, summary["comparison"])}
            return result
