"""Whole-utterance command grammar. No substring matches or partial execution."""

import re
import unicodedata
from dataclasses import dataclass

from .motion import SCENE_ACTIONS, Action

ALIASES = {
    "walk": "前进|向前走|往前走|向前走走|moveforward",
    "backward": "后退|向后走|往后走|往后退|退后|movebackward",
    "turn_left": "左转|向左转|往左转|turnleft",
    "turn_right": "右转|向右转|往右转|turnright",
    "strafe_left": "左移|向左移|向左横移|往左横移|向左平移",
    "strafe_right": "右移|向右移|向右横移|往右横移|向右平移",
    "nod": "点头|点点头|点一下头",
    "shake_head": "摇头|摇摇头|摇一下头",
    "tilt_head": "歪头|歪歪头|歪一下头",
    "stop": "停止|停|停下|停下来|别动|不要动|停止动作|停止所有动作|stop",
    "sit": "坐下|坐下来|坐着",
    "stand": "站起|站起来|站起来吧|起立",
    "roulade": "前滚翻|做个前滚翻|翻个跟头|向前翻滚",
    "ground_pick": "低头啄取|触地啄取|低头啄一下|低头啄一啄|啄一下地面",
    "yawn": "打哈欠|打个哈欠|打一个哈欠",
    "idle_on": "自然待机|开启自然待机|进入自然待机|开启待机",
    "idle_off": "关闭自然待机|停止自然待机|关闭待机",
    "skate": "滑行|向前滑行|向前滑|滑一段|滑一会儿",
    "roller_crouch": "轮滑下蹲|蹲下|下蹲",
    "kick_left": "左脚踢球|用左脚踢球",
    "kick_right": "右脚踢球|用右脚踢球",
    "pick_up": "夹起物品|用嘴夹起|用嘴夹起物品|夹起小棒",
    "carry": "搬运物品|搬运小棒|搬运",
    "put_down": "放下物品|放下小棒|放下",
    "find_companion": "发现同伴|寻找同伴|找同伴",
    "duo_walk": "双鸭一起走|两只鸭一起走",
    "collide": "相向碰面|碰个面",
    "chorus": "同步合唱|一起合唱",
    "flash_step": "闪身步",
    "bear_shake": "狗熊哆嗦毛",
    "scene_skills": "动作练习场|进入动作练习场|切换到动作练习场",
    "scene_rollers": "轮滑场景|进入轮滑场景|切换到轮滑场景",
    "scene_ball": "踢球场景|进入踢球场景|切换到踢球场景",
    "scene_duo": "双鸭场景|进入双鸭场景|切换到双鸭场景",
    "scene_carry": "搬运场景|进入搬运场景|切换到搬运场景",
}
LOOKUP = {word: name for name, words in ALIASES.items() for word in words.split("|")}
NUMBER = {"一": 1, "二": 2, "两": 2, "三": 3}
BOUNDED_DURATION = {
    "walk", "backward", "turn_left", "turn_right", "strafe_left", "strafe_right",
    "nod", "shake_head", "tilt_head",
}


@dataclass(frozen=True)
class CommandPlan:
    actions: tuple[Action, ...] = ()
    reason: str = "unmatched"


def parse_commands(text: str, *, physical: bool, scene: str | None = None) -> CommandPlan:
    if not isinstance(text, str) or not text.strip() or len(text) > 160:
        return CommandPlan(reason="empty_or_long")
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()
    # Questions, conditional and negated instructions require semantic interpretation.
    if re.search(r"[?？]|如果|假如|要是|能不能|可不可以|为什么|是不是|吗|否则", text):
        return CommandPlan()
    text = re.sub(r"^(?:小鸭[子]?[,，]?|请|帮我|麻烦你)+", "", text)
    parts = re.split(r"[,，。!！;；、]|然后|接着|接下来|之后|再|最后|首先|先", text)
    parts = [p for p in parts if p]
    if not 1 <= len(parts) <= 6:
        return CommandPlan(reason="plan_limit")
    actions = []
    current = scene
    for part in parts:
        target = "a"
        member = re.match(r"^(鸭[ab]|两只鸭|两只小鸭|双鸭)", part)
        # Keep whole aliases such as “双鸭一起走” intact.
        if member and part not in LOOKUP:
            target = {"鸭a": "a", "鸭b": "b"}.get(member[1], "both")
            part = part[member.end():]
        duration = None
        timed = re.fullmatch(r"(.+?)([一二两三]|[0-9]+(?:\.[0-9]+)?)秒", part)
        if timed:
            part = timed[1]
            duration = NUMBER.get(timed[2]) or float(timed[2])
        part = re.sub(r"(?:一下|吧)$", "", part) if part not in LOOKUP else part
        name = LOOKUP.get(part)
        if not name:
            return CommandPlan()
        if duration is not None and (name not in BOUNDED_DURATION or not 0.2 <= duration <= 3):
            return CommandPlan(reason="plan_limit")
        if name in SCENE_ACTIONS and not physical:
            return CommandPlan(reason="unsupported_context")
        if target != "a" and current != "duo":
            return CommandPlan(reason="unsupported_context")
        required = (
            "skills" if name in {"roulade", "ground_pick", "yawn", "idle_on", "idle_off"}
            else "rollers" if name in {"skate", "roller_crouch"}
            else "carry" if name in {"pick_up", "carry", "put_down"}
            else "ball" if name in {"kick_left", "kick_right"}
            else "duo" if name in {"find_companion", "duo_walk", "collide", "chorus"}
            else None
        )
        if required and current != required:
            return CommandPlan(reason="unsupported_context")
        if name.startswith("scene_"):
            current = name.removeprefix("scene_")
        elif current in {"table", "seated", "carry"} and name != "stop" and required != current:
            return CommandPlan(reason="unsupported_context")
        elif current == "rollers" and name not in {
            "skate", "roller_crouch", "nod", "shake_head", "tilt_head", "stop",
        }:
            return CommandPlan(reason="unsupported_context")
        actions.append(Action(
            name=name, target=target, **({"duration": duration} if duration else {})
        ))
    if sum(a.duration for a in actions) > 20:
        return CommandPlan(reason="plan_limit")
    return CommandPlan(tuple(actions), "matched")
