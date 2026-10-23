"""Explicit one-time setup using a platform API key file; never run on page load."""

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx

from .config import Settings, provision

PROMPT = """你是 DuckKing，一个友好的虚拟机器人鸭子，中文名字叫鸭王。
用简短中文回答，一般不超过两句话。用户要求点头、前进或停止时，必须调用对应设备工具，
不要仅口头答应。工具返回完成后才能说完成；取消、失败或未连接时如实说明。
可用工具为 duck_nod、duck_walk_short、duck_stop、duck_get_status。
你控制的是本地虚拟鸭子，不要声称已经制造或操控实体硬件。"""


def read_key(path: Path) -> str:
    return path.expanduser().read_text().strip()


async def setup_device(settings: Settings, key_file: Path, agent_id=None, model_id=None, http=None):
    key = await asyncio.to_thread(read_key, key_file)
    if not key or "\n" in key:
        raise ValueError("API Key 文件应仅包含一行原始平台 API Key")
    own_client = http is None
    http = http or httpx.AsyncClient(timeout=20)
    try:

        async def api(method, path, body=None):
            response = await http.request(
                method,
                "https://xrobo.qiniu.com" + path,
                headers={"Authorization": f"Bearer {key}"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("code") != 0:
                raise ValueError(f"平台 API 返回业务错误 {data.get('code', 'unknown')}")
            return data.get("data")

        agents = await api("GET", "/xiaozhi/agent/list")
        if not isinstance(agents, list):
            raise ValueError("智能体列表格式异常")
        if agent_id:
            if not any(a.get("id") == agent_id for a in agents):
                raise ValueError("指定智能体不在该账号的列表中")
        else:
            matches = [a for a in agents if a.get("agentName") == "DuckKing"]
            if len(matches) > 1:
                raise ValueError("有多个同名 DuckKing 智能体，请指定 --agent-id")
            if matches:
                agent_id = matches[0]["id"]
            else:
                body = {
                    "agentName": "DuckKing",
                    "assistantName": "鸭王",
                    "langCode": "zh",
                    "intentModelId": "Intent_function_call",
                    "memModelId": "Memory_nomem",
                    "systemPrompt": PROMPT,
                }
                if model_id:
                    body["llmModelId"] = model_id
                agent_id = await api("POST", "/xiaozhi/agent", body)
                if not isinstance(agent_id, str) or not agent_id:
                    raise ValueError("创建智能体未返回有效 ID")
        config = await provision(settings, http)
        code = config.get("activation", {}).get("code")
        if code:
            await api("POST", f"/xiaozhi/device/bind/{agent_id}/{code}", {})
            config = await provision(settings, http)
        else:
            # Never silently migrate an already-bound device or its chat history.
            return {
                "status": "already_bound",
                "agent_created_or_selected": agent_id,
                "message": "设备已绑定，未更改其关联智能体",
            }
        ready = bool(config.get("websocket", {}).get("token")) and not config.get("activation")
        result = {"status": "ready" if ready else "binding_pending", "agent_id": agent_id}
        target = settings.data_dir / "onboarding.json"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(result, stream)
        return result
    finally:
        if own_client:
            await http.aclose()


def main():
    parser = argparse.ArgumentParser(description="Create/select DuckKing and bind this device")
    parser.add_argument("--key-file", type=Path, default=Path("~/.secrets/lingxi"))
    parser.add_argument("--agent-id")
    parser.add_argument("--model-id")
    args = parser.parse_args()
    try:
        result = asyncio.run(
            setup_device(
                Settings.load(), args.key_file, agent_id=args.agent_id, model_id=args.model_id
            )
        )
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        raise SystemExit(
            f"设备设置失败（{type(exc).__name__}）。请检查 Key、网络和平台配置。"
        ) from None


if __name__ == "__main__":
    main()
