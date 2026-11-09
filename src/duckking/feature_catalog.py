"""One catalogue for functional scenes, their controls and the voice tool contract.

Labels are product copy. Provenance describes the actual controller, never an
assumed hardware capability. Asset readiness is reported separately at runtime.
"""

from pydantic import BaseModel, ConfigDict, Field


def item(group, title, description, category, commands, *, source, observation="proprioception"):
    return dict(
        group=group,
        title=title,
        description=description,
        category=category,
        commands=commands,
        source=source,
        observation=observation,
    )


CATALOG = {
    "movement": item(
        1,
        "认识小鸭",
        "走、转、坐下，再试试不同速度。",
        "运动",
        ["walk", "backward", "turn_left", "turn_right", "sit", "stand", "nod"],
        source="official_policy",
    ),
    "emotions": item(
        2,
        "小鸭的心情",
        "用头部、身体和声音表达情绪。",
        "表达",
        [
            "sad",
            "devastated",
            "curious",
            "mmh",
            "yes",
            "yes_fast",
            "no",
            "defiant",
            "angry",
            "mock",
            "excited",
            "impatient",
            "laugh",
        ],
        source="official_emotion_timeline",
    ),
    "director": item(
        2,
        "四鸭临场导演",
        "指定成员，轮流独唱，随时换顺序。",
        "音乐",
        ["conduct"],
        source="duckking_choreography",
    ),
    "dock": item(
        3,
        "回窝歇会儿",
        "走近、坐下对接，再离窝站起来。",
        "生活",
        ["dock", "undock"],
        source="microdock_v2",
        observation="simulated_tag_and_proprioception",
    ),
    "hop": item(
        4, "跳一下", "起跳、落地，看看有没有站稳。", "运动", ["hop"], source="happy_hop_policy"
    ),
    "flamingo": item(
        4,
        "单脚站稳",
        "抬左脚或右脚，再放回地面。",
        "运动",
        ["lift_left", "lift_right", "lower"],
        source="flamingo_cycle_policy",
    ),
    "senses": item(
        5,
        "小鸭看见什么",
        "看第一视角，观察前方距离和遮挡。",
        "感知",
        ["observe", "look_left", "look_right", "look_forward"],
        source="mujoco_camera_and_raycast",
        observation="rgb_and_raycast",
    ),
    "theremin": item(
        6,
        "距离变成音乐",
        "移动面前的物体，距离决定音高。",
        "音乐",
        ["play", "near", "far"],
        source="duckking_distance_instrument",
        observation="raycast",
    ),
    "step": item(
        7,
        "跨过小门槛",
        "跨上 25 毫米门槛，再恢复站稳。",
        "运动",
        ["cross"],
        source="step_up_policy_pair",
    ),
    "search": item(
        8,
        "三色寻宝",
        "从相机画面找到指定颜色，走近后停下。",
        "感知",
        ["find_red", "find_blue", "find_green"],
        source="rgb_visual_servo_and_official_gait",
        observation="rgb",
    ),
    "soccer": item(
        8,
        "先找球，再踢球",
        "小鸭先用相机找球，再尝试踢球。",
        "感知",
        ["kick_left", "kick_right"],
        source="rgb_visual_servo_and_official_kick",
        observation="rgb",
    ),
    "navigation": item(
        9,
        "去那里等我",
        "记住地点，绕开障碍，到点停下。",
        "生活",
        ["go_door", "go_home", "go_table"],
        source="duckking_map_navigation",
        observation="simulated_map_and_pose",
    ),
    "footsteps": item(
        9,
        "踩着标记走",
        "规划落脚点，比较目标和实际足迹。",
        "运动",
        ["steps"],
        source="footstepnet_and_footsteps",
    ),
    "swing": item(
        10, "自己荡秋千", "用身体动作让秋千荡起来。", "实验", ["swing"], source="swing_pump_policy"
    ),
    "circus": item(
        10,
        "三鸭一起跳绳",
        "摇绳与跳跃配合，观察实际接触。",
        "实验",
        ["jump_rope"],
        source="circus_policies_and_phase_controller",
        observation="proprioception_and_rope_phase",
    ),
}


class FeatureCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    operation: str = "start"
    action: str | None = None
    duration: float = Field(default=3, ge=0.5, le=36)
    speed: float = Field(default=0.18, ge=0.02, le=0.3)
    order: list[str] = Field(
        default_factory=lambda: ["a", "b", "c", "d"], min_length=1, max_length=8
    )
    request_id: str | None = Field(default=None, min_length=1, max_length=100)

    def check(self, capability):
        if capability not in CATALOG:
            raise ValueError("未知功能场景")
        if self.operation not in {"start", "stop", "reset", "status"}:
            raise ValueError("不支持的功能场景操作")
        if self.operation == "start" and self.action not in CATALOG[capability]["commands"]:
            raise ValueError("当前场景不支持这个动作，请使用页面列出的指令")
        if any(member not in {"a", "b", "c", "d"} for member in self.order):
            raise ValueError("合唱成员必须为 A、B、C 或 D")
        return self


def voice_tools(capability):
    entry = CATALOG[capability]
    schema = FeatureCommand.model_json_schema()
    schema["properties"]["operation"]["enum"] = ["start", "stop", "reset", "status"]
    schema["properties"]["action"] = {"type": "string", "enum": entry["commands"]}
    schema["properties"].pop("request_id")
    if capability != "movement":
        for field in ("duration", "speed"):
            schema["properties"].pop(field)
    if capability == "director":
        schema["properties"]["order"]["items"] = {
            "type": "string", "enum": ["a", "b", "c", "d"]
        }
    else:
        schema["properties"].pop("order")
    return [
        {
            "name": "duck_feature",
            "description": (
                f"当前功能场景：{entry['title']}。{entry['description']} "
                f"可执行动作：{', '.join(entry['commands'])}。start 执行有时限任务，stop 取消，"
                "status 查询本轮实际结果，reset 显式重置。受理不等于完成，"
                "必须按 verified 和失败原因"
                "回答。pending=true 表示还在执行，不得说已成功。不能声称临时训练出新技能。"
                "回窝只有仿真接通与虚拟电量，不是真实电气充电。"
                "只有四鸭导演的 order 选择成员次序，成员用小写 a/b/c/d；"
                "只有认识小鸭提供 duration（仿真秒数）和 speed（米/秒），其他技能时长固定。"
                "音乐为本地播放，语音理解与对话才来自灵矽。"
            ),
            "inputSchema": schema,
        }
    ]
