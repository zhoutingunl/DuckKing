"""Bounded paired seesaw execution shared by local controls and Linx MCP."""

import asyncio
import json
import logging
import secrets
import time
from pathlib import Path

from .model_assets import geometry
from .seesaw import DT, DURATION, WEIGHT_MASS, SeesawWorld
from .seesaw_policy import SeesawPolicy

logger = logging.getLogger("uvicorn.error")
HOLD_DEADBAND_M = 0.008

SEESAW_TOOLS = [
    {
        "name": "duck_seesaw",
        "description": (
            "跷跷板人机PK：左鸭听用户指挥，右鸭由PPO自主控制。"
            "说前进、向前走请调用duck_walk_short；后退用duck_backward；"
            "站住用duck_hold_position。也可以nudge direction=forward/backward/hold，"
            "首次移动会从待开始状态启动18秒真人PK；比赛中只改变左鸭，不重开或暂停右鸭。"
            "动作默认2秒、可指定1至3秒，到时结束定时移动；新指令替换旧指令。"
            "左侧默认有工程辅助站定：到时或说站住后，用小步纠偏保持当时位置。"
            "这不是PPO，也不保证瞬间静止或不摔倒；右侧PPO保持原样。"
            "start assist=false可关闭辅助，届时零速步态可能沿斜板漂移。"
            "start开始新一轮，默认mode=duel，controller=trained；seed不传则随机，左右同种子。"
            "mode=compare是规则基线对照，不接受人类插入控制；需明确重新开始PK。"
            "controller early/center/rule/baseline分别为早期PPO/回中/配平板面/官方站定。"
            "explore是左鸭不计分练习、右鸭站定，不会执行PPO。"
            "停止或失败后不能用移动指令偷偷重置：请明确start重开；reset仅重置，stop暂停两侧。"
            "status查询真实结果；只有phase=success才成功，start返回仅表示受理。"
            "鸭脚接触改变板角，橙色280克配重沿无电机滑轨移动；目标是最后连续1秒"
            "停在红色区±4厘米、速度低于2.5厘米/秒，板角小于2度且有脚支撑。"
            "forward向绿色端，backward向赭色端；不随摄像机角度改变。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["start", "stop", "status", "reset", "nudge", "explore"],
                },
                "controller": {
                    "type": "string",
                    "enum": ["trained", "early", "baseline", "center", "rule"],
                },
                "mode": {"type": "string", "enum": ["compare", "duel"]},
                "assist": {"type": "boolean", "description": "左侧工程辅助站定，默认开启"},
                "seed": {"type": "integer", "minimum": 0, "maximum": 9999},
                "direction": {"type": "string", "enum": ["forward", "backward", "hold"]},
                "seconds": {"type": "integer", "minimum": 1, "maximum": 3},
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
    }
]


# Scene-specific aliases keep familiar motion words discoverable to the cloud.
# They never enter the generic motion queue or move the PPO-controlled right duck.
SEESAW_MOVES = {
    "duck_walk_short": ("forward", "向前走、前进、往前一点：只控制左鸭向绿色端走。"),
    "duck_backward": ("backward", "后退、向后走、往后一点：只控制左鸭向赭色端退。"),
    "duck_hold_position": ("hold", "站住、站定、不走了：左鸭结束定时移动，"
                           "按本轮设置辅助站定或给零速指令，右侧PPO继续。"),
}
SEESAW_TOOLS += [
    {
        "name": name,
        "description": description + (
            "默认2秒，可用duration指定1至3秒；到时按本轮辅助设置尽量站定，可能仍有漂移。"
            "首次移动会自动开始真人PK，比赛中不会重置任何一侧。"
            "返回只表示指令受理，不能声称走动完成或停靠成功；失败或暂停后需明确重新开始。"
            if direction != "hold" else
            "只改变站定指令，不保证瞬间停稳；不重开比赛，停止整个场景请用duck_stop。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {} if direction == "hold" else {
                "duration": {"type": "integer", "minimum": 1, "maximum": 3, "default": 2}
            },
            "additionalProperties": False,
        },
    }
    for name, (direction, description) in SEESAW_MOVES.items()
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
        # Display-only paint: preserve the evaluated physics identity and policy.
        # Bump the visual cache key so previously cached green docks turn red.
        self.revision = "seesaw-" + self.world.fingerprint[:24] + "-red1"
        self.geom_ids = [
            g
            for g in range(self.world.model.ngeom)
            if self.world.model.geom_group[g] == 2
            or self.world.model.geom(g).name.startswith("seesaw_")
            and self.world.model.geom(g).name != "seesaw_floor"
        ]
        self.visual = {"revision": self.revision, **geometry(self.world.model, self.geom_ids)}
        for geom in self.visual["geoms"]:
            if self.world.model.geom(geom["id"]).name.startswith("seesaw_dock"):
                geom["rgba"] = [0.85, 0.08, 0.10, 1.0]
        self.lock, self.commands = asyncio.Lock(), asyncio.Lock()
        self.task, self.policy = None, None
        self.closed = self.stopping = False
        self.phase = self.baseline_phase = "idle"
        self.controller, self.mode = "baseline", "compare"
        self.info = self.baseline_info = self.error = None
        self.revision_number = 0
        self.request_version = 0
        self.trace = []
        self.human_action, self.human_until = 0, 0.0
        self.human_assist = True
        self.human_hold_target = None
        self.human_speed = 0.0

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
            "start": {"controller", "seed", "mode", "assist"},
            "reset": {"seed"},
            "nudge": {"direction", "seconds", "controller", "seed", "assist"},
            "explore": {"direction", "seconds", "assist"},
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
            "center",
        ):
            raise ValueError("未知任务控制器")
        if op in {"nudge", "explore"} and args.get("direction") not in (
            "forward", "backward", "hold"
        ):
            raise ValueError("请选择前进、后退或站定")
        if "mode" in args and args["mode"] not in ("compare", "duel"):
            raise ValueError("请选择规则对照或人机PK")
        if "assist" in args and type(args["assist"]) is not bool:
            raise ValueError("辅助站定必须为布尔值")
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
            first_move = None
            if op == "nudge":
                async with self.lock:
                    if self.mode == "duel":
                        if {"seed", "controller", "assist"} & args.keys():
                            raise ValueError("进行中的移动不能改变种子、辅助或右侧控制器")
                        if self.stopping or self.baseline_phase != "running":
                            raise ValueError("左侧PK已结束或暂停，请明确重新开始PK")
                        self._human_command(args)
                        self.revision_number += 1
                        return self.summary()
                    if self.phase == "running" or self.baseline_phase == "running":
                        raise ValueError("规则对照进行中或正在练习；请先停止，再开始人机PK")
                    if (self.phase != "idle" or self.baseline_phase != "idle"
                            or self.world.data.time or self.baseline.data.time):
                        raise ValueError("本轮已结束或暂停，请明确重新开始人机PK")
                    if args["direction"] == "hold":
                        return self.summary()
                first_move = args
                op, args = "start", {"operation": "start", "mode": "duel", **{
                    key: args[key] for key in ("controller", "seed", "assist") if key in args
                }}
            elif op == "explore" and self.mode != "explore" and (
                    self.phase == "running" or self.baseline_phase == "running"):
                raise ValueError("挑战进行中，请先停止再练习左鸭")
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
                    seed = args.get("seed")
                    if seed is None:
                        seed = (
                            (self.world.seed + 1 + secrets.randbelow(9999)) % 10000
                            if op == "start" else self.world.seed
                        )
                    self.world.reset(seed)
                    self.baseline.reset(seed)
                    self.info = self.baseline_info = self.error = None
                    self.phase = self.baseline_phase = "idle"
                    self.trace = []
                    self.mode = "compare"
                    self.human_action, self.human_until = 0, 0.0
                    self.human_hold_target = None
                    self.human_speed = 0.0
                elif self.world.done or self.baseline.done or self.error:
                    raise ValueError("本轮已结束，请先重置跷跷板")
                self.revision_number += 1
                if op != "reset":
                    self.controller = controller if op == "start" else "baseline"
                    self.mode = args.get("mode", "compare") if op == "start" else "explore"
                    self.human_assist = args.get("assist", True)
                    self.policy = policy
                    if first_move or op == "explore":
                        self._human_command(first_move or args)
                    self.phase = "running"
                    if not self.baseline.done:
                        self.baseline_phase = "running"
                    self.stopping = False
                    self.task = asyncio.create_task(
                        self._loop(
                            int(args.get("seconds", 2) / DT)
                            if op == "explore"
                            else int(DURATION / DT),
                            {"hold": 0, "forward": 1, "backward": 2}.get(args.get("direction"), 0),
                        )
                    )
            return self.summary()

    def _human_command(self, args):
        self.human_action = {"hold": 0, "forward": 1, "backward": 2}[args["direction"]]
        self.human_until = float(self.baseline.data.time) + (
            args.get("seconds", 2) if self.human_action else 0
        )
        position = self.baseline.measure()["position_m"]
        self.human_hold_target = position if not self.human_action else None
        logger.info(
            "seesaw_left_command seed=%s direction=%s seconds=%s sim_time=%.2f x_m=%.4f assist=%s",
            self.baseline.seed, args["direction"], args.get("seconds", 2),
            self.baseline.data.time, position, self.human_assist,
        )

    def _human_control(self, position):
        if self.human_action and self.baseline.data.time >= self.human_until - 1e-9:
            self.human_action = 0
            self.human_hold_target = position
            logger.info("seesaw_left_move_expired seed=%s sim_time=%.2f hold_x_m=%.4f assist=%s",
                        self.baseline.seed, self.baseline.data.time, position, self.human_assist)
        if self.human_action or not self.human_assist:
            return self.human_action
        if self.human_hold_target is None:
            self.human_hold_target = position
        error = self.human_hold_target - position
        # Explicit human-side engineering aid. Reuses the existing discrete gait
        # commands; never changes poses, forces, trained PPO or its evaluation.
        return 1 if error > HOLD_DEADBAND_M else 2 if error < -HOLD_DEADBAND_M else 0

    def _tick(self, manual_action):
        if not self.world.done:
            obs = self.world.observation()
            action = (
                0
                if self.mode == "explore"
                else self.policy(obs)
                if self.policy
                else self.world.rule_action(obs)
                if self.controller == "rule"
                else self.world.center_action(obs)
                if self.controller == "center"
                else 0
            )
            _, _, _, _, self.info = self.world.step(action)
            if self.world.done:
                self.phase = "success" if self.info["success"] else "failed"
                if self.mode == "explore" and self.info["reason"] != "fell_or_left_board":
                    self.phase = "explored"
                    self.info.update(success=False, reason="exploration_limit")
        if not self.baseline.done:
            before = self.baseline.measure()["position_m"]
            action = (
                self._human_control(before)
                if self.mode in {"duel", "explore"}
                else self.baseline.center_action(self.baseline.observation())
                if self.mode == "compare"
                else 0
            )
            _, _, _, _, self.baseline_info = self.baseline.step(action)
            self.human_speed = (self.baseline_info["position_m"] - before) / DT
            if self.baseline.done:
                self.baseline_phase = "success" if self.baseline_info["success"] else "failed"
                if self.mode == "explore" and self.baseline_info["reason"] != "fell_or_left_board":
                    self.baseline_phase = "explored"
                    self.baseline_info.update(success=False, reason="exploration_limit")
                logger.info("seesaw_left_result seed=%s seconds=%.2f x_m=%.4f reason=%s",
                            self.baseline.seed, self.baseline.data.time,
                            self.baseline_info["position_m"], self.baseline_info["reason"])
        self.trace.append(
            {
                "seconds": max(float(self.world.data.time), float(self.baseline.data.time)),
                "position_cm": self.info["position_m"] * 100,
                "angle_deg": self.info["angle_deg"],
                "velocity_cm_s": float(self.world.command[0]) * 100,
                "contact_torque_nm": self.info["contact_torque_nm"],
                "baseline_angle_deg": self.baseline_info["angle_deg"],
                "weight_position_cm": self.info["weight_position_m"] * 100,
                "net_gravity_torque_nm": self.info["net_gravity_torque_nm"],
                "baseline_weight_position_cm": self.baseline_info["weight_position_m"] * 100,
                "baseline_position_cm": self.baseline_info["position_m"] * 100,
                "baseline_command_cm_s": float(self.baseline.command[0]) * 100,
                "baseline_actual_speed_cm_s": self.human_speed * 100,
            }
        )
        self.trace = self.trace[-int(DURATION / DT) :]

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
        self.human_action, self.human_until = 0, 0.0

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
            "load": {
                "mass_kg": WEIGHT_MASS,
                "start_position_m": world.load_start,
                "actuators": 0,
                "motion_source": "gravity and rail constraints; no target trajectory",
            },
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
            "human_command": {
                "direction": ["hold", "forward", "backward"][self.human_action],
                "remaining_seconds": max(0, self.human_until - float(self.baseline.data.time))
                if self.mode in {"duel", "explore"} and self.baseline_phase == "running"
                else 0,
                "assist_enabled": self.human_assist,
                "hold_target_m": self.human_hold_target,
                "actual_speed_m_s": self.human_speed,
                "actual_motion": "paused" if self.baseline_phase != "running" else
                "forward" if self.human_speed > 0.01 else
                "backward" if self.human_speed < -0.01 else "slow",
            },
            "error": self.error,
            "operation_failed": self.phase == "failed",
            "policy_steps": getattr(self.policy, "steps", None),
            "command_revision": self.revision_number,
            "trace": self.trace.copy(),
            "source": "MuJoCo passive hinge + frozen official gait",
            "comparison": self._summary(
                self.baseline,
                self.baseline_phase,
                self.baseline_info,
                "human"
                if self.mode == "duel"
                else "center"
                if self.mode == "compare"
                else "manual",
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
