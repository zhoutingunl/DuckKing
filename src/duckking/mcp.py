"""Linx device MCP: real results, request replay protection, and a small tool allowlist."""

import asyncio
import json
from collections import OrderedDict

from pydantic import ValidationError

from .motion import Action, MotionController
from .studio import motion_observer

TOOLS = [
    {
        "name": "duck_flash_step",
        "description": (
            "表演闪身步：预备、左闪、回闪、收势，约3秒的机器人改编动作。"
            "仅当用户明确说闪身步、闪一下时调用，不用于普通前进、左转或右转。"
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "duck_bear_shake",
        "description": (
            "表演狗熊哆嗦毛：轻蹲、四拍摆身抖头、收势，约3秒的机器人改编动作。"
            "用户说狗熊哆嗦毛、抖抖毛时调用。"
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "duck_nod",
        "description": "让鸭子点点头打招呼。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "duck_walk_short",
        "description": "让鸭子向前走一小段，到时自动停止。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "duration": {"type": "number", "minimum": 0.2, "maximum": 3, "default": 1.2}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "duck_turn_left",
        "description": "让鸭子原地向左转，到时停止；不是闪身步，不保证精确转角。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "duration": {"type": "number", "minimum": 0.2, "maximum": 3, "default": 1.2}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "duck_turn_right",
        "description": "让鸭子原地向右转，到时停止；不是闪身步，不保证精确转角。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "duration": {"type": "number", "minimum": 0.2, "maximum": 3, "default": 1.2}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "duck_stop",
        "description": "立即取消当前动作并停止移动。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "duck_get_status",
        "description": "读取当前后端类型、连接和动作状态。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]

# These are bounded commands on existing head/velocity interfaces, not new policies.
BASIC_EXTRA = {
    "duck_backward": ("backward", "向后退一小段，到时停止；不是转身。"),
    "duck_strafe_left": ("strafe_left", "向身体左侧横移一小段，不是左转或闪身步。"),
    "duck_strafe_right": ("strafe_right", "向身体右侧横移一小段，不是右转或闪身步。"),
    "duck_shake_head": ("shake_head", "左右摇头，表达否定；约1.2秒。"),
    "duck_tilt_head": ("tilt_head", "歪头表示好奇，然后回正；约1.2秒。"),
}
TOOLS += [
    {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    }
    for name, (_, description) in BASIC_EXTRA.items()
]
SKILL_TOOLS = {
    "duck_roulade": ("roulade", "动作练习场 skills：执行官方前滚翻，验证翻转并恢复站稳，最多6秒。"),
    "duck_yawn": ("yawn", "动作练习场 skills：本地抬头张嘴打哈欠，约4.5秒，不生成声音。"),
    "duck_idle_on": (
        "idle_on",
        "动作练习场 skills：开启本地自然待机，看四周、歪头和偶尔打哈欠。"
        "新动作优先，停止会关闭待机。不是视觉识别。",
    ),
    "duck_idle_off": ("idle_off", "关闭自然待机表情。只用于 skills 场景。"),
    "duck_ground_pick": (
        "ground_pick",
        "动作练习场 skills：官方低头啄取姿态，嘴尖接近地面后站起，"
        "最多5秒。仅验证姿态，未夹持物品，不能声称捡到了东西。",
    ),
    "duck_skate": (
        "skate",
        "轮滑场景 rollers：穿被动轮滑脚向前滑行，验证位移与轮子转动，滑行3秒后收势，总计最多5秒。",
    ),
    "duck_roller_crouch": ("roller_crouch", "轮滑场景 rollers：官方轮滑下蹲再站起，最多6秒。"),
}

STAGE_TOOLS = [
    {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": (
                {
                    "member": {
                        "type": "string",
                        "enum": ["a", "b", "c", "d", "selected", "leftmost"],
                        "default": "selected",
                    }
                }
                if name in {"duck_stage_gather", "duck_stage_roll", "duck_stage_dance"}
                else {}
            ),
            "additionalProperties": False,
        },
    }
    for name, description in [
        (
            "duck_stage_gather",
            "四鸭发布会：选中鸭起身集结排队后坐稳；首次未选择时召集四鸭。真实行走、哈欠和接触验收。",
        ),
        (
            "duck_stage_roll",
            "四鸭发布会：四鸭先站稳，指定 member 一起前滚翻后就地坐稳；其他鸭候场。不自动归队。"
            "a/b/c/d 按名字，selected 指屏幕多选集合（空集合请用户选择），"
            "leftmost 指屏幕最左边；需要稳定坐姿或站姿。",
        ),
        (
            "duck_stage_dance",
            "四鸭发布会：仅选中鸭先站稳，再同拍闪身步和抖毛。未选中鸭保持原位姿态；失败停止。",
        ),
    ]
]

SCENE_TOOLS = [
    *[
        {
            "name": name,
            "description": description,
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        }
        for name, (_, description) in SKILL_TOOLS.items()
    ],
    *[
        {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": ["a", "b", "both"], "default": "a"}
                },
                "additionalProperties": False,
            },
        }
        for name, description in [
            (
                "duck_sit",
                "官方坐下策略，确认身体降下、双膝折起且接触支撑后保持坐姿。"
                "只在 ball、duo 或 skills 场景使用；默认鸭 A，可选 b 或 both。"
                "坐着可以点头；行走前先站起。",
            ),
            (
                "duck_stand",
                "官方站起策略，确认站稳后才完成。只在 ball、duo 或 skills 场景使用。"
                "默认鸭 A，可选 b 或 both；失败时不能继续声称已站起或执行走路。",
            ),
        ]
    ],
    {
        "name": "duck_set_scene",
        "description": (
            "切换官方 MuJoCo 物理场景并复位。ball 单鸭踢球，duo 双鸭互动，"
            "carry 实验性嘴部搬运，skills 动作练习场，rollers 轮滑。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "scene": {"type": "string", "enum": ["ball", "duo", "carry", "skills", "rollers"]}
            },
            "required": ["scene"],
            "additionalProperties": False,
        },
    },
    {
        "name": "duck_kick",
        "description": (
            "单鸭定点踢球，必须指定 left 左脚或 right 右脚。先把球摆到所选脚前，"
            "再运行官方踢球策略；返回实际接触及位移。不能承诺距离。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"foot": {"type": "string", "enum": ["left", "right"]}},
            "required": ["foot"],
            "additionalProperties": False,
        },
    },
    *[
        {
            "name": name,
            "description": description,
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        }
        for name, description in [
            (
                "duck_pick_up",
                "嘴部搬运场景：用嘴夹起取物架上的轻质小棒，验证上下嘴接触和离架；"
                "失败不能声称拿到了。需先选择 carry 场景。",
            ),
            (
                "duck_carry",
                "已夹起物品后，夹持行走到接物台上方，最多3秒。返回真实位移和夹持结果；一次搬运后应放下。",
            ),
            (
                "duck_put_down",
                "成功搬运后，张嘴、低头、退开，将物品放到接物台；必须验证脱离嘴部并落稳，约4.5秒。",
            ),
            (
                "duck_find_companion",
                "双鸭场景中根据仿真位置、120度视野、1.2米距离和遮挡发现同伴；不是摄像头识别或真实蓝牙发现。",
            ),
            ("duck_duo_walk", "双鸭一起向各自前方行走最多3秒，处在同一物理世界。"),
            (
                "duck_collide",
                "双鸭向各自前方行走最多3秒，检查是否发生真实物理接触。初始相向站位时可碰面；不自动重置位置。",
            ),
            (
                "duck_chorus",
                "双鸭同步合唱3秒：本地合成两个声部、同步点头。需要浏览器启用合唱声音，不是灵矽生成的歌声，也不保证浏览器已播放。",
            ),
        ]
    ],
]


class DeviceMCP:
    def __init__(self, motion: MotionController, session_key: str, voice=None):
        self.motion = motion
        self.voice = voice
        self.session_key = session_key
        self.requests: OrderedDict[str, tuple[str, asyncio.Task]] = OrderedDict()

    async def handle(self, request: dict, *, observe=None) -> dict | None:
        if "id" not in request:
            return None
        request_id = request["id"]
        response = {"jsonrpc": "2.0", "id": request_id}
        if request.get("jsonrpc") != "2.0" or not isinstance(request_id, (int, str)):
            return response | {"error": {"code": -32600, "message": "Invalid request"}}
        key = json.dumps(request_id)
        fingerprint = json.dumps(request, sort_keys=True)
        if key in self.requests:
            previous, task = self.requests[key]
            if previous != fingerprint:
                return response | {"error": {"code": -32600, "message": "Request ID reused"}}
            return await asyncio.shield(task)
        task = asyncio.create_task(self._dispatch(request, response, observe))
        self.requests[key] = (fingerprint, task)
        if len(self.requests) > 200:
            # Never drop an in-flight call; the voice transport also bounds concurrency.
            for old_key, (_, old_task) in list(self.requests.items()):
                if old_task.done() and len(self.requests) > 200:
                    self.requests.pop(old_key)
        return await asyncio.shield(task)

    async def _dispatch(self, request, response, observe=None):
        method = request.get("method")
        params = request.get("params") or {}
        if not isinstance(params, dict):
            return response | {"error": {"code": -32602, "message": "Invalid params"}}
        if method == "initialize":
            return response | {
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "DuckKing", "version": "0.1.0"},
                }
            }
        if method == "tools/list":
            tools = TOOLS
            if self.motion.backend.kind == "mujoco":
                tools = TOOLS + SCENE_TOOLS
                if self.motion.backend.scene == "stage":
                    tools = [
                        t for t in TOOLS if t["name"] in {"duck_stop", "duck_get_status"}
                    ] + STAGE_TOOLS
            if self.motion.studio:
                if self.motion.studio.active not in {None, "voice", "persona"}:
                    tools = [t for t in tools if t["name"] in {"duck_stop", "duck_get_status"}]
                tools = tools + self.motion.studio.tools()
                if self.motion.studio.active and self.voice:
                    tools = tools + self.voice.profile_tools()
            return response | {"result": {"tools": tools}}
        if method != "tools/call":
            return response | {"error": {"code": -32601, "message": "Method not found"}}
        try:
            name, arguments = params.get("name"), params.get("arguments", {})
            if not isinstance(name, str):
                raise ValueError("工具名称必须是字符串")
            if not isinstance(arguments, dict):
                raise ValueError("工具参数必须为对象")
            if (self.motion.backend.kind == "mujoco" and self.motion.backend.scene == "stage"
                    and name not in {t["name"] for t in STAGE_TOOLS}
                    and name not in {"duck_stop", "duck_get_status"}):
                raise ValueError("四鸭发布会请使用当前集结、翻滚和齐舞工具")
            if self.voice and name == "duck_voice_style":
                result = await self.voice.set_style(arguments)
                return response | {
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                        ],
                        "isError": False,
                    }
                }
            studio = self.motion.studio
            if studio:
                studio.helpers.guard(name)
                if studio.active and name == "duck_set_scene":
                    raise ValueError("互动舞台已准备好，请使用当前节目工具；换幕请在页面选择")
                if studio.active == "coach" and name == "duck_kick":
                    raise ValueError("教练场景请用 duck_coach，观察、摆球和踢球必须分开")
                if (studio.active not in {None, "voice", "persona"}
                        and name not in {"duck_stop", "duck_get_status"}
                        and name not in {t["name"] for t in studio.tools()}):
                    raise ValueError("请使用当前节目提供的工具，不能绕过任务约束")
            if studio and name in {t["name"] for t in studio.tools()}:
                first_action = None

                def observed(event, action_id, result=None):
                    nonlocal first_action
                    if first_action is None and event == "action_start":
                        first_action = action_id
                    if observe and action_id == first_action:
                        observe(event, tool=name, **({"result": result} if result else {}))

                token = motion_observer.set(observed)
                try:
                    result = await studio.invoke(name, arguments)
                finally:
                    motion_observer.reset(token)
                return response | {
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                        ],
                        "isError": result.get("operation_failed", False),
                    }
                }
            if name.startswith("duck_stage_") and (
                self.motion.backend.kind != "mujoco" or self.motion.backend.scene != "stage"
            ):
                raise ValueError("请先准备四鸭发布会舞台")
            allowed = (
                {"duration"}
                if name in {"duck_walk_short", "duck_turn_left", "duck_turn_right"}
                else set()
            )
            if self.motion.backend.kind == "mujoco":
                allowed = (
                    {"target"}
                    if name in {"duck_sit", "duck_stand"}
                    else {"scene"}
                    if name == "duck_set_scene"
                    else {"foot"}
                    if name == "duck_kick"
                    else allowed
                )
            if name in {"duck_stage_gather", "duck_stage_roll", "duck_stage_dance"}:
                allowed = {"member"}
            if set(arguments) - allowed:
                raise ValueError("工具包含不支持的参数")
            if name == "duck_get_status":
                state = await self.motion.snapshot()
                result = {
                    "backend": {k: v for k, v in state["backend"].items() if k != "geoms"},
                    "action": state["action"],
                    **({"studio": state["studio"]} if "studio" in state else {}),
                }
            else:
                kind = {
                    **{key: value[0] for key, value in BASIC_EXTRA.items()},
                    "duck_stage_gather": "stage_gather",
                    "duck_stage_roll": "stage_roll",
                    "duck_stage_dance": "stage_dance",
                    "duck_nod": "nod",
                    "duck_walk_short": "walk",
                    "duck_turn_left": "turn_left",
                    "duck_turn_right": "turn_right",
                    "duck_stop": "stop",
                    "duck_flash_step": "flash_step",
                    "duck_bear_shake": "bear_shake",
                }.get(name)
                if self.motion.backend.kind == "mujoco":
                    if name == "duck_set_scene":
                        if arguments.get("scene") not in {
                            "ball",
                            "duo",
                            "carry",
                            "skills",
                            "rollers",
                        }:
                            raise ValueError("场景必须为 ball、duo、carry、skills 或 rollers")
                        kind, arguments = "scene_" + arguments["scene"], {}
                    elif name == "duck_kick":
                        if arguments.get("foot") not in {"left", "right"}:
                            raise ValueError("踢球必须明确指定 left 左脚或 right 右脚")
                        kind, arguments = "kick_" + arguments["foot"], {}
                    else:
                        kind = {
                            **{key: value[0] for key, value in SKILL_TOOLS.items()},
                            "duck_sit": "sit",
                            "duck_stand": "stand",
                            "duck_find_companion": "find_companion",
                            "duck_duo_walk": "duo_walk",
                            "duck_collide": "collide",
                            "duck_chorus": "chorus",
                            "duck_pick_up": "pick_up",
                            "duck_carry": "carry",
                            "duck_put_down": "put_down",
                        }.get(name, kind)
                if not kind:
                    raise ValueError("未知工具")
                if name in {"duck_stage_gather", "duck_stage_roll", "duck_stage_dance"}:
                    stage = self.motion.backend.stage
                    reference = stage.voice_reference
                    member = arguments.get("member", "selected")
                    if reference and member in {"selected", "leftmost"}:
                        if member == "selected":
                            members = list(reference[0])
                            if not members and name == "duck_stage_gather":
                                members = list("abcd")
                            arguments = {"members": members}
                        else:
                            arguments = {"member": reference[1]}
                action = Action(
                    name=kind, request_id=f"{self.session_key}:{request['id']}", **arguments
                )
                await self.motion.submit(action)
                if observe:
                    observe("action_start", tool=name)
                try:
                    result = await self.motion.wait(action.request_id)
                except asyncio.CancelledError:
                    if observe:
                        observe("action_end", tool=name, result="cancelled")
                    raise
                if observe:
                    observe("action_end", tool=name, result=result["status"])
            failed = result.get("status") in {"failed", "cancelled"}
            return response | {
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                    "isError": failed,
                }
            }
        except (ValueError, ValidationError, OSError) as exc:
            return response | {
                "result": {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            }

    async def close(self):
        tasks = [task for _, task in self.requests.values() if not task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
