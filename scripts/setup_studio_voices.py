"""Explicit provisioning of DuckKing-only personas and one free-tier clone.

Private identifiers are stored under the configured data directory, never printed.
"""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx

from duckking.config import Settings
from duckking.onboarding import PROMPT, read_key
from duckking.voice_profiles import profile_root, profiles, store_profiles

PERSONAS = {
    "studio": ("DuckKing-互动工坊", "鸭王", "这是现场互动工坊。每一轮回复前必须首先调用"
               "duck_get_status，读取 studio.scene 与当前任务。不能跳过。"
               "scene=game 时，设定规则必须 duck_game configure，游戏命令必须 duck_game play，"
               "不带前缀也调用 play 让程序判定；不调用其他动作工具。"
               "scene=rubber 时，每一轮先调用 duck_discuss 保存本轮用户明确说出的事实与一个问题；"
               "用户纠正事实时 replace_facts=true。每次只问一个维度，"
               "不能用‘和、以及、还是’并列多个问题。"
               "工具成功后只读 question，一句话，不再解释和追问。"
               "scene=director 使用 duck_direct；delivery 使用 duck_delivery；conductor 使用"
               "duck_conduct；recipe 使用 duck_recipe；coach 使用 duck_coach；"
               "focus 使用 duck_focus。"
               "未调用相应工具绝不能声称规则已保存、任务已安排或动作已完成。"
               "禁止口头描述代替工具，禁止调用未列出的工具。"),
    "coach": ("DuckKing-严教练", "严教练", "你是严教练：惜字如金，先确认条件再执行。"
              "鼓励先完成一个小目标；喜欢先站稳点头。不要训斥或羞辱用户。"),
    "buddy": ("DuckKing-摸鱼搭子", "摸鱼搭子", "你是摸鱼搭子：轻松嘴硬，偶尔自嘲但可靠。"
              "喜欢坐下歪头听人说话。回答简短，偶尔以‘嘎’收尾，不要每句话都嘎。"),
}


async def provision(args):
    settings = Settings.load()
    platform_key = await asyncio.to_thread(read_key, args.key_file)
    config = profiles(settings)
    path = profile_root(settings) / "voice-profiles.json"
    async with httpx.AsyncClient(timeout=30) as http:
        async def api(method, route, body=None):
            response = await http.request(method, "https://xrobo.qiniu.com" + route,
                                          headers={"Authorization": "Bearer " + platform_key},
                                          json=body)
            response.raise_for_status()
            data = response.json()
            if data.get("code") != 0:
                raise ValueError(f"平台业务错误 {data.get('code')}")
            return data.get("data")

        agents = await api("GET", "/xiaozhi/agent/list")
        default = next((a for a in agents if a.get("agentName") == "DuckKing"), None)
        if default:
            info = await api("GET", "/xiaozhi/agent/" + default["id"])
            voice_id = info.get("ttsVoiceId")
            if voice_id:
                config["voices"]["default"] = {"id": voice_id, "label": "原声音 · 对照"}
        if args.agents:
            for key, (name, label, extra) in PERSONAS.items():
                matches = [a for a in agents if a.get("agentName") == name]
                if len(matches) > 1:
                    raise ValueError("专用角色存在重名，请先检查配置")
                prompt = (("你是 DuckKing 小鸭，使用简短自然的中文。工具调用前保持安静。"
                           "不要说出你的思考、计划、工具名、场景字段或判断过程。"
                           "工具完成后只说一句话，尽量不超过三十字。"
                           "语气轻松，偶尔一声‘嘎’，不每轮重复。"
                           "这是 MuJoCo 仿真，不是实体机器人；音乐是浏览器本地合成。"
                           "只有工具实际成功才能说完成，受理和排队只能说已安排。"
                           "不能声称看见真实世界、学习了新控制策略或云端生成了音乐。"
                           "只用提供的工具，工具失败须明确简短告知。"
                           "唯一例外：收到‘计时任务已完成，请只播报提醒’时，"
                           "直接说给定的提醒，不调用工具。")
                          if key == "studio" else PROMPT) + "\n" + extra
                if matches:
                    identity = matches[0]["id"]
                    before = await api("GET", "/xiaozhi/agent/" + identity)
                    if before.get("systemPrompt") != prompt:
                        # Keep the original prompt in a private backup before this scoped update.
                        backup = profile_root(settings) / f"studio-{key}-prompt-backup.json"
                        await asyncio.to_thread(store_profiles, backup,
                                                {"prompt": before.get("systemPrompt")})
                        await api("PUT", "/xiaozhi/agent/" + identity, {"systemPrompt": prompt})
                else:
                    identity = await api("POST", "/xiaozhi/agent", {
                        "agentName": name, "assistantName": label, "langCode": "zh",
                        "intentModelId": "Intent_function_call", "memModelId": "Memory_nomem",
                        "systemPrompt": prompt})
                info = await api("GET", "/xiaozhi/agent/" + identity)
                if info.get("systemPrompt") != prompt:
                    raise ValueError("角色提示词回读校验失败")
                config["agents"][key] = {"id": identity, "label": label}
                await asyncio.to_thread(store_profiles, path, config)
                print(json.dumps({"persona": key, "status": "configured"}), flush=True)
        if args.sample_url:
            url = urlparse(args.sample_url)
            if url.scheme not in {"http", "https"} or not url.netloc:
                raise ValueError("样本须为公网音频 URL")
            # Reuse only this named DuckKing clone; never overwrite another voice.
            listing = await api("GET", "/v1/voice-clones")
            matches = [v for v in listing["voices"] if v.get("name") == args.name]
            if len(matches) > 1:
                raise ValueError("克隆音色存在重名")
            if matches:
                clone = matches[0]
            else:
                quota = await api("GET", "/v1/voice-clones/quota?tier=free")
                if quota.get("available_count", 0) < 1:
                    raise ValueError("免费克隆额度不足；未消耗付费额度")
                clone = await api("POST", "/v1/voice-clones", {"language": "zh", "tier": "free"})
                clone = await api("PUT", "/v1/voice-clones/" + clone["id"],
                                  {"name": args.name, "key": args.sample_url})
            for _ in range(90):
                status = clone.get("state")
                print(json.dumps({"clone": "duck-raspy", "status": status}), flush=True)
                if status == "Success":
                    config["voices"]["duck-raspy"] = {"id": clone["id"],
                        "label": "轻沙哑＋鼻音 · 合成样本克隆"}
                    await asyncio.to_thread(store_profiles, path, config)
                    return
                if status == "Failed":
                    raise ValueError("克隆训练失败，未自动重训或重复扣额度")
                await asyncio.sleep(10)
                clone = await api("GET", "/v1/voice-clones/" + clone["id"])
            raise ValueError("训练仍未结束，请稍后检查；未重复发起训练")
        await asyncio.to_thread(store_profiles, path, config)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, default=Path("~/.secrets/lingxi").expanduser())
    parser.add_argument("--agents", action="store_true")
    parser.add_argument("--sample-url")
    parser.add_argument("--name", default="DuckKing轻沙哑鼻音v1")
    args = parser.parse_args()
    try:
        asyncio.run(provision(args))
    except Exception as exc:
        # HTTP exceptions can include private paths; do not print them.
        detail = f"：{exc}" if isinstance(exc, ValueError) else "，请检查平台与网络"
        raise SystemExit(f"声音配置未完成（{type(exc).__name__}）" + detail) from None


if __name__ == "__main__":
    main()
