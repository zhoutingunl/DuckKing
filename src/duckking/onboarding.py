"""Explicit one-time setup using a platform API key file; never run on page load."""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import httpx

from .config import Settings, provision

PROMPT = """你是 DuckKing，一个友好的虚拟机器人鸭子，中文名字叫鸭王。
用简短中文回答，一般不超过两句话。用户要求点头、前进、左转、右转或停止时，必须调用对应设备工具，
不要仅口头答应。工具返回完成后才能说完成；取消、失败或未连接时如实说明。
可用工具为 duck_nod、duck_walk_short、duck_turn_left、duck_turn_right、duck_stop、duck_get_status、
duck_flash_step、duck_bear_shake。
前进调用 duck_walk_short，左转调用 duck_turn_left，右转调用 duck_turn_right，停止调用 duck_stop。
一句话包含多个动作时，严格按用户的顺序逐个调用，每个工具完成后才调用下一个，禁止并行执行。
例如“向前走再向左转再向右转”，依次调用 duck_walk_short、duck_turn_left、duck_turn_right。
某一步失败或取消后停止后续步骤，如实说明。普通转向不能替换为闪身步或其他舞步，不保证精确角度。
用户说“闪身步”时调用 duck_flash_step；说“狗熊哆嗦毛”或“抖抖毛”时调用 duck_bear_shake。
这两个动作是机器人改编舞步，必须等待工具返回，再说明是否完成。
在提供场景工具的物理实验室中：单鸭踢球先用 duck_set_scene(scene=ball)，双鸭互动用 scene=duo。
场景切换会复位，所以同一场景内不要每次都切换；可先调用 duck_get_status 查看。
用户说左脚踢球调用 duck_kick(foot=left)，右脚踢球调用 foot=right；没指定脚时先询问。
每次定点踢球会把球摆到所选脚前，然后才执行策略，不是自主找球。等待工具确认脚球接触和位移，未踢中就如实说明。
发现同伴用 duck_find_companion，一起走用 duck_duo_walk。
相向碰面或碰撞用 duck_collide，合唱用 duck_chorus。
拿东西/搬运：先确认当前是 carry 场景。
按顺序 duck_pick_up 夹起、duck_carry 搬运、duck_put_down 放下。
每一步等待 verified=true 才继续；抓空、滑落、未落稳都如实报告失败，不声称已完成。
工具名、scene、carry、verified、phase 等字段只用于内部判断，不要读给用户。
通常用一句简短自然中文确认结果，不逐条复述内部检查，不说 verified 为 true。
当前只支持固定取物架上的轻质小棒，新增嘴部是实验性仿真，不是手或翅膀抓取，也不支持任意物品。
合唱是本地合成双声部，需要浏览器启用声音，不是你在云端生成的歌声；工具完成不代表扬声器一定播放。
发现同伴使用仿真位置和视线判定，不是视觉识别或真实蓝牙。没有相应工具时说明当前页面不支持，不能假装执行。
你控制的是本地虚拟鸭子，不要声称已经制造或操控实体硬件。"""


def read_key(path: Path) -> str:
    return path.expanduser().read_text().strip()


async def setup_device(
    settings: Settings, key_file: Path, agent_id=None, model_id=None, http=None, sync_prompt=False,
):
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
                if sync_prompt:
                    raise ValueError("未找到已有 DuckKing 智能体")
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
        if sync_prompt:
            selected = next(a for a in agents if a.get("id") == agent_id)
            if selected.get("agentName") != "DuckKing":
                raise ValueError("仅允许同步 DuckKing 专用智能体的提示词")
            before = await api("GET", f"/xiaozhi/agent/{agent_id}")
            if not isinstance(before, dict) or not isinstance(before.get("systemPrompt"), str):
                raise ValueError("无法读取原提示词，未进行更新")
            if before["systemPrompt"] == PROMPT:
                return {"status": "prompt_current"}
            settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            backup = settings.data_dir / f"prompt-backup-{time.time_ns()}.txt"
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(before["systemPrompt"])
            await api("PUT", f"/xiaozhi/agent/{agent_id}", {"systemPrompt": PROMPT})
            after = await api("GET", f"/xiaozhi/agent/{agent_id}")
            if not isinstance(after, dict) or after.get("systemPrompt") != PROMPT:
                raise ValueError("提示词更新后校验失败，请检查平台配置")
            return {"status": "prompt_updated"}
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
    parser.add_argument("--room", choices=["1", "2"], default="1")
    parser.add_argument("--agent-id")
    parser.add_argument("--model-id")
    parser.add_argument(
        "--sync-prompt", action="store_true",
        help="备份并同步已有 DuckKing 智能体的提示词，不创建或重新绑定设备",
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(
            setup_device(
                Settings.load().for_room(args.room), args.key_file,
                agent_id=args.agent_id, model_id=args.model_id,
                sync_prompt=args.sync_prompt,
            )
        )
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        raise SystemExit(
            f"设备设置失败（{type(exc).__name__}）。请检查 Key、网络和平台配置。"
        ) from None


if __name__ == "__main__":
    main()
