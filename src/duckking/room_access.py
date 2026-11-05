"""Anonymous, process-local room sessions. Tokens never enter JSON or logs."""

import base64
import hashlib
import hmac
import re
import secrets
from contextvars import ContextVar

COOKIE_NAME = "duckking_session"
current_owner: ContextVar[str | None] = ContextVar("duckking_room_owner", default=None)


class RoomSessions:
    def __init__(self):
        self.key = secrets.token_bytes(32)

    def encode(self, owner):
        signature = base64.urlsafe_b64encode(
            hmac.digest(self.key, owner.encode(), hashlib.sha256)
        ).decode().rstrip("=")
        return owner + "." + signature

    def issue(self):
        owner = secrets.token_urlsafe(24)
        return owner, self.encode(owner)

    def read(self, value):
        if not isinstance(value, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{32}\.[A-Za-z0-9_-]{43}", value
        ):
            return None
        owner = value.split(".", 1)[0]
        return owner if hmac.compare_digest(value, self.encode(owner)) else None
