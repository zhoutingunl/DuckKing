"""One browser owns one explicit Linx session. Never synthesize fake cloud replies."""

import asyncio
import base64
import json
import time
import uuid
from contextlib import suppress

import httpx
from websockets.asyncio.client import connect

from .config import Settings, provision, secure_device_endpoint
from .diagnostics import VoiceDiagnostics
from .mcp import DeviceMCP
from .motion import Action, MotionController
from .opus import OpusCodec

RECORDING_LIMIT = 15.0
RESPONSE_TIMEOUT = 20.0
PLAYBACK_TIMEOUT = 15.0
TURN_TIMEOUT = 60.0
WATCHDOG_INTERVAL = 0.25
IO_TIMEOUT = 5.0
CONNECT_TIMEOUT = 35.0


class VoiceSession:
    def __init__(self, send, motion: MotionController, settings: Settings, diagnostics=None):
        self.send = send
        self.motion = motion
        self.settings = settings
        self.cloud = None
        self.reader: asyncio.Task | None = None
        self.watchdog: asyncio.Task | None = None
        self.connector: asyncio.Task | None = None
        self.tasks: set[asyncio.Task] = set()
        self.mcp = DeviceMCP(motion, uuid.uuid4().hex[:12])
        self.encoder = self.decoder = None
        self.session_id = ""
        self.state = "disconnected"
        self.activation_code = ""
        self.error = ""
        self.started = 0.0
        self.audio_format = "opus"
        self.sample_rate = 16000
        self.diagnostics = diagnostics or VoiceDiagnostics()
        self.turn = self.uplink_frames = self.downlink_frames = 0
        self.last_activity = self.state_since = time.monotonic()
        self.logged_state = None

    def record(self, event, **fields):
        self.diagnostics.record(
            event, state=self.state, turn=self.turn, uplink_frames=self.uplink_frames,
            downlink_frames=self.downlink_frames,
            elapsed_ms=int(max(0, time.monotonic() - self.started) * 1000) if self.turn else 0,
            **fields,
        )

    def diagnostic_status(self):
        return {
            "state": self.state, "turn": self.turn,
            "state_elapsed_seconds": round(time.monotonic() - self.state_since, 1),
            "uplink_frames": self.uplink_frames, "downlink_frames": self.downlink_frames,
            "response_timeout_seconds": RESPONSE_TIMEOUT,
        }

    def status(self):
        return {"state": self.state, "activation_code": self.activation_code, "error": self.error}

    def _record_state(self):
        if self.logged_state != self.state:
            self.state_since = time.monotonic()
            self.logged_state = self.state
            self.record("state")
    async def publish_status(self):
        self._record_state()
        await self.send({"type": "voice_status", **self.status()})

    def start_connect(self, *, recovering=False):
        if self.connector is None or self.connector.done():
            self.connector = asyncio.create_task(self.open(recovering=recovering))

    async def open(self, *, recovering=False):
        await self.disconnect()
        self.mcp = DeviceMCP(self.motion, uuid.uuid4().hex[:12])
        self.state = "recovering" if recovering else "connecting"
        self.error = "上一轮已结束，正在重新连接；不会重发录音。" if recovering else ""
        self.activation_code = ""
        await self.publish_status()
        try:
            await asyncio.wait_for(self._open_transport(), CONNECT_TIMEOUT)
        except Exception as exc:
            self.record("connection_error", error_type=type(exc).__name__)
            await self.disconnect()
            self.state = "error"
            # Network exceptions can contain URLs or authorization data; report only their type.
            self.error = f"连接未成功，请检查绑定、额度与网络（{type(exc).__name__}）"
            await self.publish_status()

    async def _open_transport(self):
        async with httpx.AsyncClient(timeout=15) as http:
            config = await provision(self.settings, http)
        activation = config.get("activation", {}).get("code")
        if activation:
            self.activation_code = str(activation)
            self.state = "awaiting_binding"
            await self.publish_status()
            return
        address, token = config["websocket"]["url"], config["websocket"]["token"]
        if not token:
            raise ValueError("missing device token")
        address = secure_device_endpoint(address)
        identity = config["identity"]
        self.encoder = OpusCodec(16000)
        self.cloud = await connect(
            address,
            additional_headers={
                "Authorization": f"Bearer {token}",
                "Device-Id": identity["device_id"],
                "Client-Id": identity["client_id"],
                "Protocol-Version": "1",
            },
            open_timeout=10,
            max_size=1024 * 1024,
            ping_interval=20,
        )
        await self._json(
            {
                "type": "hello",
                "version": 1,
                "transport": "websocket",
                "features": {"mcp": True},
                "audio_params": {
                    "format": "opus",
                    "sample_rate": 16000,
                    "channels": 1,
                    "frame_duration": 60,
                    "play_buffer_duration": 1000,
                },
            }
        )
        hello = json.loads(await asyncio.wait_for(self.cloud.recv(), 10))
        if hello.get("type") != "hello" or hello.get("transport") != "websocket":
            raise ValueError("invalid hello")
        params = hello.get("audio_params") or {}
        self.sample_rate = params.get("sample_rate", 16000)
        self.audio_format = params.get("format", "opus")
        if params.get("channels", 1) != 1 or self.audio_format not in {"opus", "pcm"}:
            raise ValueError("unsupported audio parameters")
        self.decoder = OpusCodec(self.sample_rate)
        self.session_id = hello.get("session_id", "")
        self.state = "ready"
        self.error = ""
        self.last_activity = time.monotonic()
        await self.publish_status()
        self.reader = asyncio.create_task(self._receive())
        self.watchdog = asyncio.create_task(self._watch())

    async def _json(self, data: dict):
        if not self.cloud:
            raise ValueError("灵矽尚未连接")
        await asyncio.wait_for(
            self.cloud.send(json.dumps(data, ensure_ascii=False)), IO_TIMEOUT
        )

    async def listen(self, start: bool):
        if start:
            if self.state != "ready":
                raise ValueError("请等待灵矽连接就绪或回答结束")
            self.started = time.monotonic()
            self.last_activity = self.started
            self.turn += 1
            self.uplink_frames = self.downlink_frames = 0
            self.state = "listening"
        elif self.state == "listening":
            self.state = "thinking"
        else:
            return
        self.last_activity = time.monotonic()
        self.record("listen_start" if start else "listen_stop")
        await self._json(
            {
                "session_id": self.session_id,
                "type": "listen",
                "state": "start" if start else "stop",
                "mode": "manual",
            }
        )
        await self.publish_status()

    async def audio(self, pcm: bytes):
        if self.state != "listening":
            return
        if time.monotonic() - self.started > RECORDING_LIMIT:
            await self.listen(False)
            return
        if len(pcm) != 1920:
            raise ValueError("音频帧必须是 16kHz / 60ms / PCM16 单声道")
        await asyncio.wait_for(self.cloud.send(self.encoder.encode(pcm)), IO_TIMEOUT)
        self.uplink_frames += 1
        if self.uplink_frames == 1:
            self.record("uplink_first_frame")

    async def _tool(self, payload):
        params = payload.get("params")
        tool = params.get("name") if isinstance(params, dict) else None
        self.record("tool_start", method=payload.get("method"), tool=tool)
        try:
            result = await self.mcp.handle(payload)
            if result is not None:
                await self._json({"type": "mcp", "session_id": self.session_id, "payload": result})
            failed = result and ("error" in result or result.get("result", {}).get("isError"))
            self.record(
                "tool_end", tool=tool,
                result="ignored" if result is None else "error" if failed else "ok",
            )
        except Exception as exc:
            self.record("tool_end", tool=tool, result="error", error_type=type(exc).__name__)
            # The session's receive loop reports connection failures, not a fabricated tool result.
            return

    async def _receive(self):
        try:
            async for message in self.cloud:
                if isinstance(message, bytes):
                    self.last_activity = time.monotonic()
                    pcm = self.decoder.decode(message) if self.audio_format == "opus" else message
                    if len(pcm) % 2:
                        raise ValueError("odd PCM payload")
                    self.downlink_frames += 1
                    if self.downlink_frames == 1:
                        self.record("downlink_first_frame")
                    await self.send(
                        {
                            "type": "audio",
                            "sample_rate": self.sample_rate,
                            "pcm": base64.b64encode(pcm).decode(),
                        }
                    )
                    continue
                data = json.loads(message)
                kind = data.get("type")
                if kind == "mcp":
                    self.last_activity = time.monotonic()
                    payload = data.get("payload")
                    if not isinstance(payload, dict):
                        raise ValueError("invalid MCP payload")
                    if len(self.tasks) >= 32:
                        raise ValueError("too many concurrent tool calls")
                    task = asyncio.create_task(self._tool(payload))
                    self.tasks.add(task)
                    task.add_done_callback(self.tasks.discard)
                elif kind == "stt":
                    self.last_activity = time.monotonic()
                    self.record("stt", text_chars=len(data.get("text", "")))
                    await self.send(
                        {"type": "transcript", "role": "user", "text": data.get("text", "")}
                    )
                elif kind == "tts":
                    if data.get("state") == "start":
                        if self.state == "ready":
                            self.started = time.monotonic()
                        self.last_activity = time.monotonic()
                        self.state = "speaking"
                        self.record("tts_start")
                    elif data.get("state") == "stop":
                        self.state = "ready"
                        self.record("tts_stop")
                        await self.send(
                            {"type": "playback_end", "aborted": bool(data.get("is_aborted"))}
                        )
                    elif data.get("state") == "sentence_start":
                        self.last_activity = time.monotonic()
                        self.record("tts_sentence", text_chars=len(data.get("text", "")))
                        await self.send(
                            {
                                "type": "transcript",
                                "role": "assistant",
                                "text": data.get("text", ""),
                            }
                        )
                    await self.publish_status()
            final_state, error = "disconnected", "灵矽连接已结束，点击重新连接"
            self.record("connection_closed")
        except asyncio.CancelledError:
            return
        except Exception as exc:
            final_state, error = "error", f"语音连接中断（{type(exc).__name__}），请重新连接"
            self.record("connection_error", error_type=type(exc).__name__)
        await self.disconnect()
        self.state, self.error = final_state, error
        with suppress(OSError, RuntimeError):
            await self.send({"type": "playback_end", "aborted": True})
            await self.publish_status()

    async def _watch(self):
        try:
            while True:
                await asyncio.sleep(WATCHDOG_INTERVAL)
                now = time.monotonic()
                if self.state == "listening" and now - self.started >= RECORDING_LIMIT:
                    self.record("timeout", reason="recording_limit")
                    await self.listen(False)
                elif self.state in {"thinking", "speaking"}:
                    reason = None
                    if now - self.started >= TURN_TIMEOUT:
                        reason = "turn_limit"
                    elif now - self.last_activity >= (
                        RESPONSE_TIMEOUT if self.state == "thinking" else PLAYBACK_TIMEOUT
                    ):
                        reason = "response_idle" if self.state == "thinking" else "playback_idle"
                    if reason:
                        self.record("timeout", reason=reason)
                        await self.reset()
                        return
        except asyncio.CancelledError:
            return
        except Exception as exc:
            await self.command_failed(exc)

    async def reset(self, *, manual=False):
        if manual:
            self.record("reset", reason="manual")
        await self.disconnect()
        await self.send({"type": "playback_end", "aborted": True})
        self.start_connect(recovering=True)

    async def command_failed(self, error):
        self.record("command_error", error_type=type(error).__name__)
        await self.disconnect()
        self.state = "error"
        self.error = "语音指令发送失败，已停止本轮，请重新连接。"
        await self.send({"type": "playback_end", "aborted": True})
        await self.publish_status()

    async def _stop_motion(self):
        record = await self.motion.submit(Action(name="stop"))
        await self.motion.wait(record["id"])

    async def disconnect(self):
        for name in ("connector", "watchdog", "reader"):
            task = getattr(self, name)
            if task is asyncio.current_task():
                continue
            setattr(self, name, None)
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        await self.mcp.close()
        if self.cloud:
            await self._stop_motion()
            with suppress(OSError, TimeoutError):
                await asyncio.wait_for(self.cloud.close(), IO_TIMEOUT)
            self.cloud = None
        for codec in (self.encoder, self.decoder):
            if codec:
                codec.close()
        self.encoder = self.decoder = None
        self.session_id = ""
        self.state = "disconnected"
        self._record_state()
