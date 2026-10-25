"""Persistent bounded recipes, editable rules, and small conversational state."""

import asyncio
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Literal

from pydantic import Field

from .studio import Routine, Strict


class Recipe(Strict):
    operation: Literal["draft", "confirm", "run", "delete", "list"]
    name: str = Field(
        default="下班", min_length=1, max_length=20, pattern=r"^[\w\u4e00-\u9fff -]+$")
    plan: Routine | None = None


class Game(Strict):
    operation: Literal["configure", "play", "stop", "status"]
    prefix: str = Field(default="鸭王说", min_length=2, max_length=12)
    plan: Routine | None = None


class Discussion(Strict):
    fact: str = Field(min_length=1, max_length=200)
    replace_facts: bool = False
    question: str = Field(min_length=1, max_length=120)


class Focus(Strict):
    operation: Literal["start", "extend", "cancel", "status"]
    seconds: int = Field(default=10, ge=5, le=3600)


def normalized(text):
    return re.sub(r"[\s，。！？、,.!?：:；;\"'“”‘’]", "", text).casefold()


def save_recipes(path, recipes):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix="recipes-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(recipes, stream, ensure_ascii=False)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def load_recipes(path):
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or len(data) > 20:
        raise ValueError("动作配方文件格式错误")
    for name, value in data.items():
        Recipe(operation="run", name=name)
        Routine.model_validate(value["plan"])
        if not isinstance(value["version"], int) or value["version"] < 1:
            raise ValueError("动作配方版本错误")
    return data


class StudioTasks:
    def __init__(self, studio):
        self.studio = studio
        self.recipes = None
        self.draft = None
        self.prefix = None
        self.score = {"accepted": 0, "refused": 0}
        self.facts = []
        self.question = ""
        self.deadline = None
        self.timer_event = asyncio.Event()

    def snapshot(self):
        return {"recipes": self.recipes or {}, "draft": self.draft,
                "game": {"prefix": self.prefix, **self.score},
                "discussion": {"facts": list(self.facts), "question": self.question},
                "focus_remaining_s": max(0, round(self.deadline - time.monotonic(), 1))
                if self.deadline is not None else None}

    def reset(self):
        self.prefix = None
        self.deadline = None
        self.timer_event.set()
        self.facts.clear()
        self.question = ""
        self.draft = None

    def guard(self, name):
        if self.studio.active == "game" and self.prefix and name not in {
            "duck_game", "duck_get_status", "duck_stop", "duck_task",
        }:
            raise ValueError("鸭王说游戏中必须通过规则工具检查本轮原话，不能绕过口令执行")

    async def recipe(self, command, *, manual=False):
        s = self.studio
        if self.recipes is None:
            self.recipes = await asyncio.to_thread(load_recipes, s.data_dir / "recipes.json")
        if command.operation == "draft":
            if command.plan is None:
                raise ValueError("请提供完整的新动作配方")
            if len(self.recipes) >= 20 and command.name not in self.recipes:
                raise ValueError("最多保存 20 个暗号，请先删除一个")
            self.draft = {"name": command.name, "plan": command.plan.model_dump(), "turn": s.turn,
                          "version": self.recipes.get(command.name, {}).get("version", 0) + 1}
            return {"message": "请复述草稿并等待用户下一轮确认，不要立即保存或执行",
                    "draft": self.draft}
        if command.operation == "confirm":
            if not self.draft or command.name != self.draft["name"]:
                raise ValueError("没有对应的待确认草稿")
            if not manual and s.turn <= self.draft["turn"]:
                raise ValueError("需要用户下一轮明确确认，不能在提出配方的同一轮自动确认")
            self.recipes[command.name] = {k: self.draft[k] for k in ("plan", "version")}
            await asyncio.to_thread(save_recipes, s.data_dir / "recipes.json", self.recipes)
            self.draft = None
        elif command.operation == "delete":
            if command.name not in self.recipes:
                raise ValueError("没有这个暗号")
            del self.recipes[command.name]
            await asyncio.to_thread(save_recipes, s.data_dir / "recipes.json", self.recipes)
        elif command.operation == "run":
            if command.name not in self.recipes:
                raise ValueError("没有这个暗号，请先教我并确认保存")
            entry = self.recipes[command.name]
            plan = Routine.model_validate(entry["plan"])
            async def perform():
                s.state["recipe_version"] = entry["version"]
                return await s.routine(plan)
            return await s.start("recipe", perform)
        return {"message": "配方已保存" if command.operation == "confirm" else "配方列表已更新",
                "recipes": self.recipes, "draft": self.draft}

    async def game(self, command):
        s = self.studio
        if command.operation == "configure":
            self.prefix = command.prefix
            self.score = {"accepted": 0, "refused": 0}
        elif command.operation == "stop":
            self.prefix = None
        elif command.operation == "play":
            if not self.prefix:
                raise ValueError("请先设定游戏口令")
            if not normalized(s.transcript).startswith(normalized(self.prefix)):
                self.score["refused"] += 1
                return {"accepted": False, "message": "缺少当前口令，本轮没有执行动作",
                        "game": self.snapshot()["game"]}
            if command.plan is None:
                raise ValueError("请提供口令后的动作计划")
            self.score["accepted"] += 1
            return await s.start("game", lambda: s.routine(command.plan))
        return {"message": "规则已更新", "game": self.snapshot()["game"]}

    async def discuss(self, command):
        if command.question.count("？") + command.question.count("?") > 1:
            raise ValueError("每轮最多一个追问")
        if command.replace_facts:
            self.facts.clear()
        if command.fact not in self.facts:
            self.facts.append(command.fact)
        self.facts = self.facts[-8:]
        self.question = command.question
        s = self.studio
        async def gesture():
            result = await s.move("nod" if command.replace_facts else "tilt_head")
            s.state["results"].append(result)
            return {"facts": list(self.facts), "question": self.question,
                    "message": "请只向用户提出这个问题，不追加一串检查步骤"}
        return await s.start("rubber", gesture)

    async def focus(self, command):
        s = self.studio
        if command.operation == "status":
            return self.snapshot()
        if command.operation == "cancel":
            await s.external(None)
            await s.move("stop")
            self.deadline = None
        elif command.operation == "extend":
            if self.deadline is None or not s.task or s.task.done():
                raise ValueError("当前没有正在等待的提醒")
            if self.deadline - time.monotonic() + command.seconds > 3600:
                raise ValueError("提醒最多延后到一小时内")
            self.deadline += command.seconds
            self.timer_event.set()
        elif command.operation == "start":
            async def timer():
                try:
                    s.state["results"].append(await s.move("sit"))
                    self.deadline = time.monotonic() + command.seconds
                    while self.deadline > time.monotonic():
                        self.timer_event.clear()
                        try:
                            await asyncio.wait_for(self.timer_event.wait(),
                                                   self.deadline - time.monotonic())
                        except TimeoutError:
                            break
                    s.state["results"].append(await s.move("stand"))
                    if s.announce:
                        await s.announce("专注时间到了，起来活动一下吧。")
                    return {"verified": True, "message": "已到期并站稳，提醒一次"}
                finally:
                    self.deadline = None
            await s.start("focus", timer)
            return {"message": "已安排提醒；坐稳后开始计时", **s.snapshot()}
        return self.snapshot()
