"""Local identity and optional private settings. Public responses never expose tokens."""

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path("~/.local/share/duckking").expanduser())
    secrets_file: Path = field(default_factory=lambda: Path("~/.secrets/duckking.env").expanduser())
    ota_url: str = "https://xrobo.qiniuapi.com/v1/ota/"
    ws_url: str = ""
    ws_token: str = field(default="", repr=False)
    device_id: str = ""
    client_id: str = ""

    @classmethod
    def load(cls):
        path = Path(os.getenv("DUCKKING_SECRETS_FILE", "~/.secrets/duckking.env")).expanduser()
        values = dict(dotenv_values(path)) if path.is_file() else {}
        values.update(os.environ)
        return cls(
            data_dir=Path(values.get("DUCKKING_DATA_DIR", "~/.local/share/duckking")).expanduser(),
            secrets_file=path,
            ota_url=values.get("LINX_OTA_URL", cls.ota_url),
            ws_url=values.get("LINX_WS_URL", ""),
            ws_token=values.get("LINX_WS_TOKEN", ""),
            device_id=values.get("LINX_DEVICE_ID", ""),
            client_id=values.get("LINX_CLIENT_ID", ""),
        )

    def identity(self) -> dict:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.data_dir / "identity.json"
        if path.exists():
            saved = json.loads(path.read_text())
        else:
            # Stable locally administered pseudo-MAC derived from host NIC identity.
            digest = bytearray(hashlib.sha256(str(uuid.getnode()).encode()).digest()[:6])
            digest[0] = (digest[0] | 2) & 0xFE
            saved = {
                "device_id": ":".join(f"{x:02x}" for x in digest),
                "client_id": str(uuid.uuid4()),
            }
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(saved, f)
        identity = {
            "device_id": self.device_id or saved["device_id"],
            "client_id": self.client_id or saved["client_id"],
        }
        if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", identity["device_id"]):
            raise ValueError("LINX_DEVICE_ID 必须是 MAC 地址格式")
        if uuid.UUID(identity["client_id"]).version != 4:
            raise ValueError("LINX_CLIENT_ID 必须是 UUIDv4")
        return identity


def validate_endpoint(url: str, websocket=False):
    parts = urlparse(url)
    secure, local = ("wss", "ws") if websocket else ("https", "http")
    if parts.scheme != secure and not (
        parts.scheme == local and parts.hostname in {"127.0.0.1", "localhost"}
    ):
        raise ValueError("云端地址必须使用 TLS；无加密地址仅用于本机协议测试")
    if not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError("无效的服务地址")


def secure_device_endpoint(url: str) -> str:
    parts = urlparse(url)
    # The live OTA gateway currently returns ws:// for its official endpoint.
    # That same documented host supports TLS; never send device tokens in plaintext.
    if (
        parts.scheme == "ws"
        and parts.hostname == "xrobo-io.qiniuapi.com"
        and parts.port in {None, 80}
    ):
        if parts.username or parts.password:
            raise ValueError("无效的服务地址")
        url = parts._replace(scheme="wss", netloc="xrobo-io.qiniuapi.com").geturl()
    validate_endpoint(url, websocket=True)
    return url


async def provision(settings: Settings, http) -> dict:
    identity = settings.identity()
    if settings.ws_url and settings.ws_token:
        address = secure_device_endpoint(settings.ws_url)
        return {
            "websocket": {"url": address, "token": settings.ws_token},
            "identity": identity,
        }
    validate_endpoint(settings.ota_url)
    headers = {
        "Activation-Version": "1",
        "Device-Id": identity["device_id"],
        "Client-Id": identity["client_id"],
        "User-Agent": "duckking/0.1.0",
        "Accept-Language": "zh-CN",
    }
    body = {
        "version": 0,
        "mac_address": identity["device_id"],
        "uuid": identity["client_id"],
        "application": {
            "name": "duckking",
            "version": "0.1.0",
            "elf_sha256": hashlib.sha256(b"duckking/0.1.0").hexdigest(),
        },
        "board": {"type": "duckking-desktop", "ssid": "", "rssi": 0},
    }
    response = await http.post(settings.ota_url, headers=headers, json=body)
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError("OTA 返回内容无效")
    result["identity"] = identity
    return result
