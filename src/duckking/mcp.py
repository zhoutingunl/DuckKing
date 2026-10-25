"""Linx device MCP: real results, request replay protection, and a small tool allowlist."""

import asyncio
import json
from collections import OrderedDict

from pydantic import ValidationError

from .motion import Action, MotionController

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

SCENE_TOOLS = [
    *[
        {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": {"target": {"type": "string", "enum": ["a", "b", "both"],
                                            "default": "a"}},
                "additionalProperties": False,
            },
        }
        for name, description in [
            ("duck_sit", "官方坐下策略，确认身体降下、双膝折起且接触支撑后保持坐姿。"
             "只在 ball 或 duo 场景使用；默认鸭 A，可选 b 或 both。坐着可以点头；行走前先站起。"),
            ("duck_stand", "官方站起策略，确认站稳后才完成。只在 ball 或 duo 场景使用。"
             "默认鸭 A，可选 b 或 both；失败时不能继续声称已站起或执行走路。"),
        ]
    ],
    {
        "name": "duck_set_scene",
        "description": (
            "切换官方 MuJoCo 物理场景并复位。ball 单鸭踢球，duo 双鸭互动，carry 实验性嘴部搬运。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"scene": {"type": "string", "enum": ["ball", "duo", "carry"]}},
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
    def __init__(self, motion: MotionController, session_key: str):
        self.motion = motion
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
            return response | {"result": {"tools": tools}}
        if method != "tools/call":
            return response | {"error": {"code": -32601, "message": "Method not found"}}
        try:
            name, arguments = params.get("name"), params.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("工具参数必须为对象")
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
            if set(arguments) - allowed:
                raise ValueError("工具包含不支持的参数")
            if name == "duck_get_status":
                state = await self.motion.snapshot()
                result = {
                    "backend": {k: v for k, v in state["backend"].items() if k != "geoms"},
                    "action": state["action"],
                }
            else:
                kind = {
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
                        if arguments.get("scene") not in {"ball", "duo", "carry"}:
                            raise ValueError("场景必须为 ball、duo 或 carry")
                        kind, arguments = "scene_" + arguments["scene"], {}
                    elif name == "duck_kick":
                        if arguments.get("foot") not in {"left", "right"}:
                            raise ValueError("踢球必须明确指定 left 左脚或 right 右脚")
                        kind, arguments = "kick_" + arguments["foot"], {}
                    else:
                        kind = {
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
