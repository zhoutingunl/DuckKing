"""Operator-provisioned language identities, independent within each visitor room."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import httpx

from .onboarding import read_key, setup_device
from .voice_profiles import language_agent, profiles


def device_settings(settings, language):
    if not isinstance(language, str) or language not in {"zh", "en", "fr", "ja"}:
        raise ValueError("不支持的对话语言")
    # Never carry another language's static token or identity overrides over.
    return replace(settings, data_dir=settings.data_dir / "languages" / language,
                   ws_url="", ws_token="", device_id="", client_id="")


def voice_settings(settings, language, agent_id):
    entry = profiles(settings)["agents"].get(f"language_{language}", {})
    if entry.get("transport") != "bound_device":
        return settings
    selected = device_settings(settings, language)
    try:
        marker = json.loads((selected.data_dir / "binding.json").read_text())
        identity = json.loads((selected.data_dir / "identity.json").read_text())
        if (marker != {"language": language, "agent_id": agent_id,
                       "device_id": identity["device_id"]}):
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("当前语言的语音设备尚未准备，请联系管理员。") from None
    return selected


async def setup_language_device(settings, key_file: Path, language, *, http=None):
    """Bind a new private identity explicitly; never rebind an existing device."""
    agent_id = language_agent(settings, language)
    if not agent_id:
        raise ValueError("请先配置语言智能体")
    selected = device_settings(settings, language)
    own = http is None
    http = http or httpx.AsyncClient(timeout=25)
    try:
        await setup_device(selected, key_file, agent_id=agent_id, lang_code=language, http=http)
        # setup_device deliberately leaves already-bound devices alone. Verify
        # that such an identity is bound to this language, instead of assuming it.
        key = await asyncio.to_thread(read_key, key_file)
        response = await http.get(f"https://xrobo.qiniu.com/xiaozhi/device/bind/{agent_id}",
                                  headers={"Authorization": f"Bearer {key}"})
        response.raise_for_status()
        packet = response.json()
        identity = selected.identity()
        if (packet.get("code") != 0 or not isinstance(packet.get("data"), list)
                or not any(isinstance(device, dict)
                           and device.get("macAddress") == identity["device_id"]
                           for device in packet["data"])):
            (selected.data_dir / "binding.json").unlink(missing_ok=True)
            raise ValueError("语言设备绑定校验失败，未启用")
        marker = selected.data_dir / "binding.json"
        marker.touch(mode=0o600)
        marker.chmod(0o600)
        marker.write_text(json.dumps({"language": language, "agent_id": agent_id,
                                      "device_id": identity["device_id"]}))
        return {"status": "language_device_ready", "language": language,
                "voice_verified": False, "existing_room_binding_changed": False}
    finally:
        if own:
            await http.aclose()
