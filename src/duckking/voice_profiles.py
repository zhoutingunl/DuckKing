"""Private, operator-provisioned voice and agent allowlists; public keys never expose IDs."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VoiceStyle(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    profile: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    pitch: float = Field(default=1.0, ge=.5, le=2)
    speed: float = Field(default=1.0, ge=.5, le=2)
    emotion: Literal["neutral", "happy", "sad", "angry"] = "neutral"


class PersonaChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    persona: Literal["default", "coach", "buddy"]


def profile_root(settings):
    path = settings.data_dir
    return path.parent.parent if path.parent.name == "rooms" else path


def profiles(settings):
    path = profile_root(settings) / "voice-profiles.json"
    if not path.is_file():
        return {"voices": {}, "agents": {}}
    data = json.loads(path.read_text())
    for group in ("voices", "agents"):
        entries = data.get(group, {})
        if not isinstance(entries, dict) or len(entries) > 10:
            raise ValueError("私有声音配置格式错误")
        for key, entry in entries.items():
            if (not isinstance(entry, dict) or not isinstance(entry.get("id"), str)
                    or not entry["id"].strip() or len(entry["id"]) > 128
                    or any(c in entry["id"] for c in "\r\n")):
                raise ValueError("私有声音配置无效")
            if group == "voices":
                VoiceStyle(profile=key)
    return {"voices": data.get("voices", {}), "agents": data.get("agents", {})}


def public_profiles(settings):
    config = profiles(settings)
    return {"voices": [{"key": key, "label": item.get("label", key)}
                       for key, item in config["voices"].items()],
            "personas": [{"key": key, "label": item.get("label", key)}
                         for key, item in config["agents"].items()]}


def store_profiles(path: Path, config):
    from .studio_tasks import save_recipes
    save_recipes(path, config)
