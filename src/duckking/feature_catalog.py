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
    "acrobatics": item(
        10,
        "倒立头旋连续技",
        "后滚翻、倒立、左右头旋，再自己站起来。",
        "运动",
        ["routine", "backroll", "headstand", "spin_left", "spin_right"],
        source="reble2421_acrobatics_cpu_benchmark",
    ),
    "sprint_race": item(
        10,
        "两米冲线",
        "用基础步态挑战两米赛道，按真实越线计时。",
        "运动",
        ["play_game"],
        source="duckking_rules_official_policy",
    ),
    "roller_race": item(
        10,
        "轮滑冲线",
        "被动轮滑跑完两米，看谁能保持直线。",
        "运动",
        ["play_game"],
        source="duckking_rules_official_policy",
    ),
    "hill_race": item(
        7,
        "八度上坡",
        "真实八度坡道，一点五米后才算越线。",
        "运动",
        ["play_game"],
        source="duckking_rules_official_policy",
    ),
    "red_light": item(
        10,
        "红灯停挑战",
        "六米赛道，红灯时移动超过三厘米就被发现。",
        "游戏",
        ["play_game"],
        source="duckking_rules_official_policy",
        observation="proprioception_and_programmed_traffic_signal",
    ),
    "tug": item(
        10,
        "双鸭拔河",
        "颈部连接真实绳索，拉向平台边缘。",
        "游戏",
        ["play_game"],
        source="duckking_rules_official_policy",
    ),
    "tof": item(
        5,
        "八乘八距离视野",
        "转头查看六十四束测距，颜色表示远近。",
        "感知",
        ["observe", "look_left", "look_right", "look_forward"],
        source="duckking_mujoco_tof_grid",
        observation="rgb_and_8x8_raycast",
    ),
    "climb": item(
        10,
        "爬梯上桌",
        "在窄梯上交替迈步，再尝试桌面起身。",
        "实验",
        ["try_climb"],
        source="playground_climber_getup",
        observation="proprioception_and_simulated_handoff",
    ),
    "chimney": item(
        10,
        "窄缝攀爬",
        "进入、支撑爬升、退出；观察哪一步最难。",
        "实验",
        ["try_climb"],
        source="playground_enter_climb_exit",
        observation="proprioception_and_relative_localization",
    ),
    "runup_roll": item(
        10,
        "助跑前滚翻",
        "先走起来，再翻滚并恢复站立。",
        "运动",
        ["try_trick"],
        source="langli11_runup_roll",
    ),
    "roller_slalom": item(
        10,
        "轮滑绕锥",
        "已知路线指挥轮滑策略绕过八个标记。",
        "运动",
        ["try_trick"],
        source="langli11_slalom",
        observation="proprioception_and_known_path",
    ),
    "roller_glide": item(
        10,
        "短暂单脚滑",
        "滑行时抬脚，按真实接触力计时。",
        "实验",
        ["try_trick"],
        source="langli11_short_glide",
    ),
    "dock_standing": item(
        3,
        "站着回窝",
        "对比站姿和坐姿，看看磁吸接通与离窝。",
        "实验",
        ["dock", "undock"],
        source="microdock_v1",
        observation="simulated_tag_and_proprioception",
    ),
    "terrain_slip": item(
        7,
        "湿滑地面",
        "低摩擦地面上，看看专门学过的步态。",
        "环境",
        ["try_course"],
        source="witcheer_slip_backlash_policy",
    ),
    "terrain_rough": item(
        7,
        "崎岖小路",
        "盲走过起伏地面，观察脚下真实高度。",
        "环境",
        ["try_course"],
        source="witcheer_rough_backlash_policy",
    ),
    "terrain_gale": item(
        7,
        "顶着风走",
        "逆风逐渐增到三牛顿，小鸭还能前进吗？",
        "环境",
        ["try_course"],
        source="witcheer_gale_backlash_policy",
    ),
    "terrain_slope": item(
        7,
        "走上缓坡",
        "走上缓坡，再看看身体如何调整。",
        "环境",
        ["try_course"],
        source="witcheer_slope_backlash_policy",
    ),
    "terrain_step": item(
        7,
        "走下小台阶",
        "从二十五毫米台阶走下来。",
        "环境",
        ["try_course"],
        source="witcheer_step_backlash_policy",
    ),
    "terrain_stairs": item(
        7,
        "连续下楼梯",
        "三个相邻台阶，看看能否连续通过。",
        "环境",
        ["try_course"],
        source="witcheer_stairs_backlash_policy",
    ),
    "giant_ball": item(
        8,
        "小鸭踢巨球",
        "用右脚踢一颗比小鸭身体还大的球。",
        "运动",
        ["try_course"],
        source="witcheer_giant_ball_backlash_policy",
    ),
    "standup": item(
        4,
        "自己站起来",
        "从仰卧或俯卧姿态恢复，看看需要多久。",
        "运动",
        ["recover_back", "recover_front"],
        source="official_alpha_stand",
    ),
    "stilts": item(
        10,
        "踩着高跷走",
        "从十厘米到两米，换一种身体学走路。",
        "运动",
        ["stilt_walk"],
        source="playground_stilt_policy_and_morphology",
    ),
    "backflip": item(
        10,
        "高台后空翻",
        "从高台翻到软垫，观察落地和恢复。",
        "实验",
        ["flip"],
        source="playground_backflip_soft_contact",
        observation="proprioception_and_known_drop",
    ),
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
    "running": item(
        10,
        "小鸭快跑",
        "跑五秒，看实际速度和侧向偏移。",
        "运动",
        ["run"],
        source="playground_running_policy",
    ),
    "basketball": item(
        10,
        "篮球上盲平衡",
        "不看球的位置，用身体感觉保持平衡。",
        "实验",
        ["balance_ball", "roll_forward"],
        source="playground_blind_lstm_policy",
        observation="proprioception_and_recurrent_memory",
    ),
    "long_jump": item(
        10,
        "跳台长跳",
        "跨过三十厘米间隙，落到较低的平台。",
        "运动",
        ["jump_gap"],
        source="playground_platform_jump_policy",
        observation="proprioception_and_known_gap_drop",
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
        schema["properties"]["order"]["items"] = {"type": "string", "enum": ["a", "b", "c", "d"]}
    else:
        schema["properties"].pop("order")
    return [
        {
            "name": "duck_feature",
            "description": (
                f"当前功能场景：{entry['title']}。{entry['description']} "
                f"可执行动作：{', '.join(entry['commands'])}。start 执行有时限任务，stop 取消，"
                "连续动作会按当前姿态继续；需要起点的项目会在新指令前自动准备，"
                "准备期间不代表已完成。status 查询实际结果，reset 仅用于用户明确要求回到起点。"
                "动作不可用时按返回原因解释，不能让用户反复点击无效按钮。受理不等于完成，"
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
