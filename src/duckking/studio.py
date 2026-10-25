"""Room-local, bounded interactive tasks. Cloud understands; tools verify execution."""

import asyncio
import copy
import time
from contextlib import suppress
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .motion import Action


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Step(Strict):
    action: Literal[
        "nod", "shake_head", "tilt_head", "look_left", "look_right", "look_forward",
        "look_down", "walk", "backward", "strafe_left", "strafe_right", "turn_left",
        "turn_right", "sit", "stand", "flash_step", "bear_shake",
    ]
    duration: float = Field(default=1.2, ge=0.2, le=3)

    def motion(self):
        values = {"name": self.action}
        if self.action not in {"sit", "stand", "flash_step", "bear_shake"}:
            values["duration"] = self.duration
        return Action(**values)


HEAD = {"nod", "shake_head", "tilt_head", "look_left", "look_right", "look_forward", "look_down"}
MOVING = {
    "walk", "backward", "strafe_left", "strafe_right", "turn_left", "turn_right", "flash_step",
}


class Routine(Strict):
    title: str = Field(min_length=1, max_length=60)
    steps: list[Step] = Field(min_length=1, max_length=6)
    head_only: bool = False
    stationary: bool = False

    @model_validator(mode="after")
    def bounded(self):
        if sum(step.motion().duration for step in self.steps) > 20:
            raise ValueError("一段表演最多 20 秒")
        names = {s.action for s in self.steps}
        if self.head_only and names - HEAD:
            raise ValueError("只用头部的表演不能包含身体动作")
        if self.stationary and names & MOVING:
            raise ValueError("原地表演不能包含移动或转向")
        return self


class Coach(Strict):
    operation: Literal["observe", "prepare", "kick"]
    foot: Literal["left", "right"] | None = None


class Conduct(Strict):
    operation: Literal["start", "queue", "stop", "status"]
    order: list[Literal["a", "b", "c", "d"]] = Field(default_factory=list, max_length=8)


class Delivery(Strict):
    operation: Literal["start", "pause", "resume", "status"]


class TaskControl(Strict):
    operation: Literal["status", "cancel"]


CATALOG = {
    "director": ("临场小导演", "ball"),
    "delivery": ("嘴硬快递员 2.0", "carry"),
    "conductor": ("评委当指挥", "seated"),
    "voice": ("鸭子的声音身份", "ball"),
    "recipe": ("我教你一个暗号", "ball"),
    "coach": ("世界杯小教练", "ball"),
    "game": ("鸭王说", "ball"),
    "rubber": ("会追问的橡皮鸭", "ball"),
    "focus": ("专注搭子", "ball"),
    "persona": ("换班不换鸭", "ball"),
}


def tool(name, description, model):
    return {"name": name, "description": description, "inputSchema": model.model_json_schema()}


class Studio:
    def __init__(self, motion, data_dir: Path):
        self.motion, self.data_dir = motion, data_dir
        from .studio_tasks import StudioTasks

        self.helpers = StudioTasks(self)
        self.announce = None
        self.active = None
        self.lock = asyncio.Lock()
        self.commands = asyncio.Lock()
        self.task = None
        self.generation = 0
        self.state = {"status": "idle", "results": []}
        self.transcript = ""
        self.turn = 0
        self.queue = []
        self.singer = None

    def tools(self):
        if not self.active:
            return []
        from .studio_tasks import Discussion, Focus, Game, Recipe

        definitions = [
            tool("duck_recipe", "动作暗号：draft 提出完整配方，下一轮用户确认后 confirm 保存；"
                 "run 执行已保存版本；修改时重新 draft。不能把编排称为训练新策略。", Recipe),
            tool("duck_game", "鸭王说规则游戏：configure 修改口令，play 根据服务器记录的本轮"
                 "识别原话检查前缀再执行 plan。不带口令不执行，不能绕过规则调用普通动作。", Game),
            tool("duck_discuss", "橡皮鸭追问：记录已确认事实 fact；修正时 replace_facts=true"
                 "撤回旧事实；question 每轮只问一个问题。用倾头或点头表达倾听。", Discussion),
            tool("duck_focus", "专注提醒：start 坐稳后计时；extend 延长秒数；cancel 取消。"
                 "到期后真实站稳并提醒一次。受理不等于已经到期。", Focus),
            tool("duck_direct", "临场编排或替换表演：将用户故事拆成 1–6 个已有动作。"
                 "只用头时 head_only=true；不移动时 stationary=true。"
                 "新计划撤销旧计划，等待实际结果。不是训练新动作。", Routine),
            tool("duck_coach", "踢球教练：observe 只读实际球位置，绝不摆球或踢球；"
                 "prepare 明确把球摆到所选脚前；kick 踢已准备的球，不自动移球。"
                 "换脚须重新明确准备。foot 为 left/right，未指定要先问。", Coach),
            tool("duck_conduct", "四鸭现场指挥。start 按 order 开唱；queue 替换尚未演唱的队列，"
                 "当前独唱唱完坐回后再换人；stop 立即停止。受理只是排队，不代表已唱完。"
                 "仅支持当前本地《欢乐颂》片段，音乐不是云端生成。", Conduct),
            tool("duck_delivery", "固定小棒递送：start 夹起搬运放下；pause 立即停住但不松嘴；"
                 "resume 从实际阶段继续，不能重新夹取。未确认放稳不能说送达。", Delivery),
            tool("duck_task", "查询或取消当前互动任务。完成必须以工具结果为准。", TaskControl),
        ]

        chosen = {"director": "duck_direct", "delivery": "duck_delivery",
                  "conductor": "duck_conduct", "recipe": "duck_recipe", "coach": "duck_coach",
                  "game": "duck_game", "rubber": "duck_discuss", "focus": "duck_focus"}
        return [t for t in definitions if t["name"] in {"duck_task", chosen.get(self.active)}]

    def heard(self, text):
        self.transcript = text[:1000]
        self.turn += 1

    def snapshot(self):
        return {"scene": self.active, "task": copy.deepcopy(self.state),
                "queue": list(self.queue), "singer": self.singer, **self.helpers.snapshot()}

    async def select(self, scene):
        if scene not in CATALOG:
            raise ValueError("未知互动节目")
        async with self.lock:
            await self._cancel("切换节目")
            self.helpers.reset()
            self.active = scene
            self.state = {"status": "idle", "results": []}
        return self.snapshot()

    async def _cancel(self, reason):
        self.generation += 1
        if self.task and not self.task.done():
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.state.update(status="cancelled", message=reason)
        self.task = None

    async def external(self, action):
        async with self.lock:
            if (self.active == "game" and action is not None
                    and action.name not in {"stop", "reset"}
                    and not action.name.startswith("scene_")):
                raise ValueError("游戏中请通过口令规则工具执行动作")
            if action and (action.name.startswith("scene_") or action.name == "reset"):
                self.active = None
                self.helpers.reset()
            reason = "已停止" if action is None or action.name == "stop" else "已被新动作替换"
            await self._cancel(reason)

    async def move(self, name, **kwargs):
        action = Action(name=name, **kwargs)
        await self.motion.submit(action, owner=self)
        result = await self.motion.wait(action.request_id)
        if result["status"] != "completed":
            raise ValueError(result.get("error", "动作已中断"))
        return result

    async def start(self, kind, run):
        async with self.lock:
            await self._cancel("已被新任务替换")
            await self.move("stop")
            generation = self.generation
            self.state = {"version": generation, "kind": kind, "status": "running",
                          "started_at": time.time(), "results": []}
            self.task = asyncio.create_task(self._run(run, generation))
            self.task.studio_result = self.state
            return self.task

    async def _run(self, run, generation):
        try:
            result = await run()
            if generation == self.generation:
                self.state.update(status="completed", message="任务已完成", outcome=result)
        except asyncio.CancelledError:
            if self.state.get("status") == "running":
                self.state.update(status="cancelled", message="任务已取消")
        except Exception as exc:
            self.state.update(status="failed", message=str(exc))
        finally:
            try:
                await self.move("stop")
            except Exception:
                self.state.update(status="failed", message="停止未得到确认")
            self.state["finished_at"] = time.time()
            self.motion.event("studio", self.state.get("message", "任务结束"))
        return {**self.snapshot(), "operation_failed": self.state["status"] != "completed"}

    async def wait(self, task):
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if not task.cancelled():
                raise
            state = copy.deepcopy(task.studio_result)
            state["status"] = "cancelled"
            return {"task": state, "operation_failed": True}

    async def routine(self, plan):
        self.state["title"] = plan.title
        for index, step in enumerate(plan.steps):
            self.state["step"] = index + 1
            # Validate every step before starting; never partially execute an invalid plan.
            action = step.motion()
            await self.motion.submit(action, owner=self)
            result = await self.motion.wait(action.request_id)
            self.state["results"].append(result)
            if result["status"] != "completed":
                raise ValueError(result.get("error", "表演已中断"))
        return {"verified": True, "completed_steps": len(plan.steps)}

    async def conduct(self):
        self.state["results"].append(await self.move("seated_ready"))
        try:
            while self.queue:
                self.singer = self.queue.pop(0)
                self.state["results"].append(await self.move("seated_solo", target=self.singer))
            return {"verified": True, "message": "本轮独唱队列已完成"}
        finally:
            self.singer = None
            self.queue.clear()

    async def delivery(self):
        grasp = self.motion.backend.grasp
        if not grasp:
            raise ValueError("请先准备嘴部搬运舞台")
        grasp.check()
        if grasp.phase == "released":
            return {"verified": True, "message": "小棒已在接物台放稳"}
        if grasp.phase == "ready":
            self.state["results"].append(await self.move("pick_up"))
        if grasp.held and not grasp.carried:
            self.state["results"].append(await self.move("carry"))
        if grasp.held and grasp.carried:
            self.state["results"].append(await self.move("put_down"))
        if grasp.phase != "released":
            raise ValueError("当前阶段无法继续递送，请检查物品或重置场景")
        return {"verified": True, "message": "已在接物台放稳", **grasp.snapshot()}

    async def invoke(self, name, arguments, *, wait=True, manual=False):
        if not isinstance(name, str):
            raise ValueError("工具名称必须是字符串")
        if not self.active:
            raise ValueError("请先选择互动节目")
        if name == "duck_task":
            command = TaskControl.model_validate(arguments)
            if command.operation == "cancel":
                await self.external(Action(name="stop"))
                await self.move("stop")
            return self.snapshot()
        from .studio_tasks import Discussion, Focus, Game, Recipe

        specialized = {"duck_recipe": ("recipe", Recipe, self.helpers.recipe),
                       "duck_game": ("game", Game, self.helpers.game),
                       "duck_discuss": ("rubber", Discussion, self.helpers.discuss),
                       "duck_focus": ("focus", Focus, self.helpers.focus)}
        if name in specialized:
            scene, model, handler = specialized[name]
            if self.active != scene:
                raise ValueError("此工具需要先选择对应的互动节目")
            command = model.model_validate(arguments)
            async with self.commands:
                result = (await handler(command, manual=manual) if name == "duck_recipe"
                          else await handler(command))
            if isinstance(result, asyncio.Task):
                return await self.wait(result) if wait else self.snapshot()
            return {**self.snapshot(), **result}
        if name == "duck_coach":
            command = Coach.model_validate(arguments)
            if self.active != "coach":
                raise ValueError("请先选择世界杯小教练")
            if command.operation == "observe":
                return {**self.snapshot(), "observation": self.motion.backend.ball_observation()}
            if command.foot is None:
                raise ValueError("请先指定左脚或右脚")
            operation = "ball_prepare_" if command.operation == "prepare" else "ball_shoot_"
            async def coach():
                result = await self.move(operation + command.foot)
                self.state["results"].append(result)
                return result["outcome"]
            task = await self.start("coach", coach)
            return await self.wait(task) if wait else self.snapshot()
        if name == "duck_conduct":
            command = Conduct.model_validate(arguments)
            if self.active != "conductor":
                raise ValueError("请先选择评委当指挥")
            if command.operation == "status":
                return self.snapshot()
            if command.operation == "stop":
                return await self.invoke("duck_task", {"operation": "cancel"})
            if not command.order:
                raise ValueError("请指定至少一位歌手")
            if command.operation == "queue":
                if not self.task or self.task.done():
                    raise ValueError("当前没有演唱，请先开始")
                self.queue[:] = command.order
                return {**self.snapshot(), "message": "后续独唱顺序已更新"}
            # start() cancels the old queue before installing this one.
            async def perform():
                self.queue[:] = command.order
                return await self.conduct()
            await self.start("conductor", perform)
            return {**self.snapshot(), "message": "演唱已受理，等待实际站稳后发声"}
        if name == "duck_delivery":
            command = Delivery.model_validate(arguments)
            if self.active != "delivery":
                raise ValueError("请先选择嘴硬快递员")
            if command.operation == "status":
                return {**self.snapshot(), "grasp": self.motion.backend.grasp.snapshot()}
            if command.operation == "pause":
                await self.external(Action(name="stop"))
                await self.move("stop")
                self.state.update(status="paused", message="已停止移动；夹持状态请看实际数据")
                return {**self.snapshot(), "grasp": self.motion.backend.grasp.snapshot()}
            grasp = self.motion.backend.grasp
            if command.operation == "start" and grasp.phase != "ready":
                raise ValueError("递送已开始，请用继续或重置，不能重复抓取")
            if command.operation == "resume" and not (grasp.held or grasp.phase == "released"):
                raise ValueError("没有可继续的夹持任务，请检查物品或重置")
            task = await self.start("delivery", self.delivery)
        elif name == "duck_direct":
            plan = Routine.model_validate(arguments)
            if self.active != "director":
                raise ValueError("请先选择临场小导演")
            task = await self.start("director", lambda: self.routine(plan))
        else:
            raise ValueError("未知互动工具")
        return await self.wait(task) if wait else self.snapshot()

    async def close(self):
        async with self.lock:
            await self._cancel("房间已关闭")
