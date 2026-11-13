"""Explicit language provisioning, separate from page loads and device binding."""

import asyncio
import json
import time
from pathlib import Path

import httpx

from .onboarding import agent_prompt, read_key
from .voice_profiles import profile_root, profiles, store_profiles


def conversation_prompt(language):
    prompt = agent_prompt(language)
    if language == "zh":
        return prompt
    # Remove the second Chinese-only response instruction as well as the intro.
    prompt = prompt.replace("简短自然中文确认", "简短自然语言确认")
    instruction = {
        "ja": "挨拶、確認、エラー、お別れも含め、常に自然な日本語で応答してください。"
              "中国語、英語、フランス語の入力も理解しますが、明示的な依頼がない限り"
              "返答は日本語を保ってください。内部のツール名を読み上げないでください。",
        "fr": "Réponds toujours en français, y compris les salutations, "
              "confirmations, erreurs et adieux. "
              "Comprends aussi l'anglais et le chinois, "
              "mais garde le français comme langue de réponse "
              "sauf demande explicite de l'utilisateur. Ne prononce pas les noms des outils.",
        "en": "Always respond in English, "
              "including greetings, confirmations, errors and farewells. "
              "Understand French and Chinese too, but keep English as the response language unless "
              "the user explicitly asks otherwise. Never speak internal tool names.",
    }[language]
    return prompt + "\n\n" + instruction


async def setup_language_profile(settings, key_file: Path, language, *, http=None):
    prompt = conversation_prompt(language)
    key = await asyncio.to_thread(read_key, key_file)
    if not key or "\n" in key:
        raise ValueError("无效的平台 Key 文件")
    own = http is None
    http = http or httpx.AsyncClient(timeout=25)
    try:
        async def api(method, path, body=None):
            response = await http.request(method, "https://xrobo.qiniu.com" + path,
                                          headers={"Authorization": f"Bearer {key}"}, json=body)
            response.raise_for_status()
            packet = response.json()
            if packet.get("code") != 0:
                raise ValueError(f"语言配置请求失败（{packet.get('code', 'unknown')}）")
            return packet["data"]

        agents = await api("GET", "/xiaozhi/agent/list")
        config = profiles(settings)
        profile_key = f"language_{language}"
        if language == "zh":
            matches = [a for a in agents if a.get("agentName") == "DuckKing"
                       and a.get("langCode", "zh") == "zh"]
            if len(matches) != 1:
                raise ValueError("请先配置唯一的中文 DuckKing 智能体")
            agent_id = matches[0]["id"]
        else:
            name = f"DuckKing-{language}"
            matches = [a for a in agents if a.get("agentName") == name]
            if len(matches) > 1:
                raise ValueError("语言智能体名称重复，未进行修改")
            voices = (await api("GET", "/v1/voices"))["voices"]
            compatible = [v for v in voices if language in v.get("tags", {}).get("languages", [])]
            if not compatible:
                raise ValueError("平台未提供所选语言的音色")
            compatible.sort(key=lambda v: (v.get("tier") not in {None, "free", "basic"},
                                           len(v.get("tags", {}).get("languages", []))))
            voice = compatible[0]
            body = {"langCode": language, "systemPrompt": prompt, "ttsVoiceId": voice["id"],
                    "intentModelId": "Intent_function_call", "memModelId": "Memory_nomem"}
            if matches:
                agent_id = matches[0]["id"]
                before = await api("GET", f"/xiaozhi/agent/{agent_id}")
                root = profile_root(settings)
                root.mkdir(parents=True, exist_ok=True, mode=0o700)
                backup = root / f"language-agent-backup-{language}-{time.time_ns()}.json"
                backup.touch(mode=0o600)
                backup.write_text(json.dumps(before))
            else:
                agent_id = await api("POST", "/xiaozhi/agent",
                                     {**body, "agentName": name, "assistantName": "DuckKing"})
            # The template's default streaming recognizer disables automatic
            # language detection. langCode alone does not enable multilingual ASR.
            await api("PUT", f"/xiaozhi/agent/{agent_id}",
                      {**body, "extra": {"asr": {"enable_auto_lang": True}}})
            after = await api("GET", f"/xiaozhi/agent/{agent_id}")
            if (after.get("langCode") != language or after.get("ttsVoiceId") != voice["id"]
                    or after.get("systemPrompt") != prompt
                    or not after.get("extra", {}).get("asr", {}).get("enable_auto_lang")):
                raise ValueError("云端语言配置校验失败，未启用此语言")
        config["agents"][profile_key] = {
            "id": agent_id, "label": language,
            **({"transport": "bound_device"} if language in {"en", "fr", "ja"} else {}),
        }
        store_profiles(profile_root(settings) / "voice-profiles.json", config)
        return {"status": "language_profile_configured", "language": language,
                "voice_verified": False, "device_binding_changed": False}
    finally:
        if own:
            await http.aclose()
