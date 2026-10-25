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
from .diagnostics import VoiceDiagnostics, redact_transcript
from .mcp import DeviceMCP
from .motion import Action, MotionController
from .opus import OpusCodec
from .voice_profiles import PersonaChoice, VoiceStyle, profiles

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
        self.mcp = DeviceMCP(motion, uuid.uuid4().hex[:12], self)
        self.encoder = self.decoder = None
        self.session_id = ""
        self.state = "disconnected"
        self.activation_code = ""
        self.error = ""
        self.started = 0.0
        self.audio_format = "opus"
        self.sample_rate = 16000
        self.diagnostics = diagnostics or VoiceDiagnostics()
        self.diagnostics.playback = None
        self.turn = self.uplink_frames = self.downlink_frames = 0
        self.last_activity = self.state_since = time.monotonic()
        self.logged_state = None
        self.state_changed = asyncio.Event()
        self.sensitive_values = set()
        self.generation = 0
        self.pending_input = None
        self.voice_style = None
        self.persona = "default"

    def profile_tools(self):
        from .studio import tool
        return [tool("duck_voice_style", "更换下轮回答的音色。只用已配置的 profile：" +
                     "、".join(profiles(self.settings)["voices"]) +
                     "。pitch 音调、speed 语速；不改变识别或智能体。", VoiceStyle)]

    async def set_style(self, arguments):
        choice = VoiceStyle.model_validate(arguments)
        entry = profiles(self.settings)["voices"].get(choice.profile)
        if not entry:
            raise ValueError("此音色尚未训练或配置成功，请先使用已就绪音色")
        self.voice_style = {"id": entry["id"], "pitch": choice.pitch,
                            "speed": choice.speed, "emotion": choice.emotion}
        self.sensitive_values.add(entry["id"])
        await self.send({"type": "voice_profile", "profile": choice.profile,
                         "message": "音色已选择，将在下一轮输入时发给灵矽"})
        return {"profile": choice.profile, "message": "下轮回答使用所选音色；本轮未强制变声"}

    def set_persona(self, arguments):
        choice = PersonaChoice.model_validate(arguments)
        if choice.persona != "default" and choice.persona not in profiles(self.settings)["agents"]:
            raise ValueError("此角色尚未配置")
        if self.state not in {"ready", "disconnected"}:
            raise ValueError("请等待当前回答结束，或先断开连接再切换角色")
        self.persona = choice.persona
        if self.cloud:
            self.start_connect(recovering=True)

    async def announce(self, text):
        # A short focus timer can expire while its initial acknowledgement is playing.
        # Wait for that turn to finish; cancellation of the owning task cancels this wait.
        deadline = time.monotonic() + RESPONSE_TIMEOUT
        while (self.cloud and self.state in {"thinking", "speaking", "listening"}
               and time.monotonic() < deadline):
            self.state_changed.clear()
            try:
                await asyncio.wait_for(self.state_changed.wait(), deadline - time.monotonic())
            except TimeoutError:
                break
        if not self.cloud or self.state != "ready":
            await self.send({"type": "studio_notice", "text": text,
                             "spoken": False, "source": "local_task"})
            return
        self.turn = self.diagnostics.next_turn()
        self.started = self.last_activity = time.monotonic()
        self.uplink_frames = self.downlink_frames = 0
        self.state = "thinking"
        self.record("task_announcement")
        await self.send({"type": "studio_notice", "text": text,
                         "spoken": None, "source": "local_task_to_linx"})
        await self._json({"type": "listen", "state": "detect", "session_id": self.session_id,
                          "text": "计时任务已完成，请只播报提醒，不调用工具：" + text,
                          **({"agent_params": {"voice": self.voice_style}}
                             if self.voice_style else {})})
        await self.publish_status()

    def record(self, event, **fields):
        self.diagnostics.record(
            event, state=self.state, turn=self.turn, uplink_frames=self.uplink_frames,
            downlink_frames=self.downlink_frames,
            elapsed_ms=int(max(0, time.monotonic() - self.started) * 1000) if self.turn else 0,
            backend=self.motion.backend.kind,
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
        return {"state": self.state, "activation_code": self.activation_code,
                "error": self.error, "generation": self.generation}

    def _record_state(self):
        self.state_changed.set()
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
        self.mcp = DeviceMCP(self.motion, uuid.uuid4().hex[:12], self)
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

    async def _open_transport(self, *, publish_ready=True):
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
        self.sensitive_values = {token, identity["device_id"], identity["client_id"]}
        config_profiles = profiles(self.settings)
        agent_key = self.persona
        if (agent_key == "default" and self.motion.studio and self.motion.studio.active
                and "studio" in config_profiles["agents"]):
            agent_key = "studio"
        self.agent_id = (config_profiles["agents"].get(agent_key, {}).get("id")
                         if agent_key != "default" else None)
        if self.persona != "default" and not self.agent_id:
            raise ValueError("所选角色尚未配置")
        if self.agent_id:
            self.sensitive_values.add(self.agent_id)
        if self.voice_style:
            self.sensitive_values.add(self.voice_style["id"])
        self.encoder = OpusCodec(16000)
        self.cloud = await connect(
            address,
            additional_headers={
                "Authorization": f"Bearer {token}",
                "Device-Id": identity["device_id"],
                "Client-Id": identity["client_id"],
                "Protocol-Version": "1",
                **({"X-Agent-ID": self.agent_id} if self.agent_id else {}),
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
        self.sensitive_values.add(self.session_id)
        self.state = "ready"
        if self.motion.studio:
            self.motion.studio.announce = self.announce
        self.error = ""
        self.last_activity = time.monotonic()
        if publish_ready:
            await self.publish_status()
        self.reader = asyncio.create_task(self._receive(self.generation))
        self.watchdog = asyncio.create_task(self._watch())

    async def _json(self, data: dict):
        if not self.cloud:
            raise ValueError("灵矽尚未连接")
        await asyncio.wait_for(
            self.cloud.send(json.dumps(data, ensure_ascii=False)), IO_TIMEOUT
        )

    async def listen(self, start: bool, *, from_interrupt=False):
        if self.pending_input is not None and not from_interrupt:
            if start and not self.pending_input["started"]:
                self.pending_input["started"] = time.monotonic()
            elif not start:
                self.pending_input["stopped"] = True
            return
        if start:
            if self.state != "ready":
                raise ValueError("请等待灵矽连接就绪或回答结束")
            self.started = time.monotonic()
            self.last_activity = self.started
            self.turn = self.diagnostics.next_turn()
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
                **({"agent_params": {"voice": self.voice_style}}
                   if start and self.voice_style else {}),
            }
        )
        await self.publish_status()

    async def audio(self, pcm: bytes):
        if self.pending_input is not None:
            pending = self.pending_input
            if not pending["started"] or pending["stopped"]:
                return
            if len(pcm) != 1920:
                raise ValueError("音频帧必须是 16kHz / 60ms / PCM16 单声道")
            if (len(pending["frames"]) >= 250
                    or time.monotonic() - pending["started"] >= RECORDING_LIMIT):
                pending["stopped"] = True
            else:
                pending["frames"].append(pcm)
            return
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

    async def _tool(self, payload, generation=None):
        if generation is not None and generation != self.generation:
            return
        params = payload.get("params")
        tool = params.get("name") if isinstance(params, dict) else None
        turn, started = self.turn, self.started
        call = self.diagnostics.sequence + 1

        def observe(event, **fields):
            # Capture the original round, including cancellation after reconnect/new speech.
            self.diagnostics.record(
                event, turn=turn, call=call, backend=self.motion.backend.kind,
                elapsed_ms=int(max(0, time.monotonic() - started) * 1000) if turn else 0,
                **fields,
            )

        self.record("tool_start", method=payload.get("method"), tool=tool)
        try:
            result = await self.mcp.handle(payload, observe=observe)
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

    async def _receive(self, generation=None):
        if generation is None:
            generation = self.generation
        try:
            async for message in self.cloud:
                if generation != self.generation:
                    return
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
                            "generation": self.generation,
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
                    task = asyncio.create_task(self._tool(payload, generation))
                    self.tasks.add(task)
                    task.add_done_callback(self.tasks.discard)
                elif kind == "stt":
                    self.last_activity = time.monotonic()
                    text = data.get("text", "")
                    if not isinstance(text, str):
                        raise ValueError("invalid STT text")
                    if self.motion.studio:
                        self.motion.studio.heard(text)
                    self.record(
                        "stt", text_chars=len(text), text=text,
                        sensitive_values=self.sensitive_values,
                    )
                    await self.send(
                        {"type": "transcript", "role": "user", "generation": self.generation,
                         "text": redact_transcript(text, self.sensitive_values)}
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
                        self.record(
                            "tts_stop", result="aborted" if data.get("is_aborted") else "ok"
                        )
                        await self.send(
                            {"type": "playback_end", "aborted": bool(data.get("is_aborted")),
                             "generation": self.generation}
                        )
                    elif data.get("state") == "sentence_start":
                        self.last_activity = time.monotonic()
                        self.record("tts_sentence", text_chars=len(data.get("text", "")))
                        await self.send(
                            {
                                "type": "transcript",
                                "generation": self.generation,
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
            await self.send({"type": "playback_end", "aborted": True,
                             "generation": self.generation})
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

    def start_interrupt(self):
        if self.pending_input is not None:
            return
        if self.state not in {"ready", "thinking", "speaking"}:
            raise ValueError("当前不能打断，请等待连接就绪")
        self.record("interrupt", reason="manual")
        self.generation += 1
        self.pending_input = {"frames": [], "started": 0.0, "stopped": False}
        self.state = "interrupting"
        self.connector = asyncio.create_task(self._interrupt())

    async def _interrupt(self):
        try:
            await self.send({"type": "playback_end", "aborted": True,
                             "generation": self.generation})
            await self.publish_status()
            # Close the old generation: the cloud's audio/tool frames carry no
            # turn ID, so abort alone cannot reliably distinguish late replies.
            if self.reader:
                self.reader.cancel()
                await asyncio.gather(self.reader, return_exceptions=True)
                self.reader = None
            await self._cancel_tools()
            if self.cloud:
                await self._stop_motion()
                with suppress(OSError, TimeoutError):
                    await asyncio.wait_for(self._json({
                        "type": "abort", "session_id": self.session_id,
                        "reason": "wake_word_detected",
                    }), 1)
            await self.disconnect(discard_input=False)
            self.mcp = DeviceMCP(self.motion, uuid.uuid4().hex[:12], self)
            self.state = "interrupting"
            async with asyncio.timeout(CONNECT_TIMEOUT):
                await self._open_transport(publish_ready=False)
                pending = self.pending_input
                if self.state != "ready":
                    # Activation is explicit; never retain audio awaiting binding.
                    self.pending_input = None
                    return
                if not pending["started"]:
                    self.pending_input = None
                    await self.publish_status()
                    return
                await self.listen(True, from_interrupt=True)
                self.started = pending["started"]
                # Keep accepting in-order input while buffered frames are sent.
                self.pending_input = pending
                sent = 0
                while sent < len(pending["frames"]):
                    pcm = pending["frames"][sent]
                    await asyncio.wait_for(self.cloud.send(self.encoder.encode(pcm)), IO_TIMEOUT)
                    self.uplink_frames += 1
                    if self.uplink_frames == 1:
                        self.record("uplink_first_frame")
                    sent += 1
                self.pending_input = None
                if pending["stopped"]:
                    await self.listen(False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.command_failed(exc)

    async def reset(self, *, manual=False):
        if manual:
            self.record("reset", reason="manual")
        await self.disconnect()
        await self.send({"type": "playback_end", "aborted": True,
                             "generation": self.generation})
        self.start_connect(recovering=True)

    async def command_failed(self, error):
        self.record("command_error", error_type=type(error).__name__)
        await self.disconnect()
        self.state = "error"
        self.error = "语音指令发送失败，已停止本轮，请重新连接。"
        await self.send({"type": "playback_end", "aborted": True,
                             "generation": self.generation})
        await self.publish_status()

    async def _stop_motion(self):
        studio = self.motion.studio
        # A spoken queue edit must not stop the singer it is meant to follow.
        # Explicit stop/disconnect still cancels the conductor immediately.
        if (studio and self.pending_input is not None and studio.active == "conductor"
                and studio.task and not studio.task.done()):
            return
        # Interrupting spoken acknowledgement should not erase a quiet reminder.
        # Explicit disconnect/stop still cancels it; a new timer command can extend it.
        preserve = (studio and self.pending_input is not None
                    and studio.active == "focus" and studio.helpers.deadline is not None)
        record = await self.motion.submit(Action(name="stop"), owner=studio if preserve else None)
        await self.motion.wait(record["id"])

    async def _cancel_tools(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        await self.mcp.close()

    async def disconnect(self, *, discard_input=True):
        if discard_input:
            self.pending_input = None
        if self.motion.studio and self.motion.studio.announce == self.announce:
            self.motion.studio.announce = None
        for name in ("connector", "watchdog", "reader"):
            task = getattr(self, name)
            if task is asyncio.current_task():
                continue
            setattr(self, name, None)
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await self._cancel_tools()
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
