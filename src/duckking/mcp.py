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
            "用户说闪身步、闪一下时调用。"
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


class DeviceMCP:
    def __init__(self, motion: MotionController, session_key: str):
        self.motion = motion
        self.session_key = session_key
        self.requests: OrderedDict[str, tuple[str, asyncio.Task]] = OrderedDict()

    async def handle(self, request: dict) -> dict | None:
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
        task = asyncio.create_task(self._dispatch(request, response))
        self.requests[key] = (fingerprint, task)
        if len(self.requests) > 200:
            # Never drop an in-flight call; the voice transport also bounds concurrency.
            for old_key, (_, old_task) in list(self.requests.items()):
                if old_task.done() and len(self.requests) > 200:
                    self.requests.pop(old_key)
        return await asyncio.shield(task)

    async def _dispatch(self, request, response):
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
            return response | {"result": {"tools": TOOLS}}
        if method != "tools/call":
            return response | {"error": {"code": -32601, "message": "Method not found"}}
        try:
            name, arguments = params.get("name"), params.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("工具参数必须为对象")
            allowed = {"duration"} if name == "duck_walk_short" else set()
            if set(arguments) - allowed:
                raise ValueError("工具包含不支持的参数")
            if name == "duck_get_status":
                state = await self.motion.snapshot()
                result = {"backend": state["backend"], "action": state["action"]}
            else:
                kind = {
                    "duck_nod": "nod",
                    "duck_walk_short": "walk",
                    "duck_stop": "stop",
                    "duck_flash_step": "flash_step",
                    "duck_bear_shake": "bear_shake",
                }.get(name)
                if not kind:
                    raise ValueError("未知工具")
                action = Action(
                    name=kind, request_id=f"{self.session_key}:{request['id']}", **arguments
                )
                await self.motion.submit(action)
                result = await self.motion.wait(action.request_id)
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
