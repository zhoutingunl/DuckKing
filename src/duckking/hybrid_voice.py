"""Local-first speech routing with all-or-nothing plans and one cloud handoff."""

import asyncio
import time
import uuid

import httpx

from . import asr_client
from .diagnostics import redact_transcript
from .local_commands import ALIASES, parse_commands
from .mcp import DeviceMCP
from .voice import IO_TIMEOUT, RECORDING_LIMIT, VoiceSession

TOOLS = {
    "walk": "duck_walk_short", "kick_left": "duck_kick", "kick_right": "duck_kick",
}


class HybridVoiceSession(VoiceSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.frames = []
        self.processing = None
        self.route = "local_ready"

    def status(self):
        return {**super().status(), "mode": "local_first", "route": self.route}

    async def open(self, *, recovering=False):
        await self.disconnect()
        self.state = "ready"
        self.error = self.activation_code = ""
        self.route = "local_ready"
        self.watchdog = asyncio.create_task(self._watch())
        await self.publish_status()

    async def listen(self, start, *, from_interrupt=False):
        if self.pending_input is not None and not from_interrupt:
            if start and not self.pending_input["started"]:
                self.pending_input["started"] = time.monotonic()
            elif not start:
                self.pending_input["stopped"] = True
            return
        if start:
            if self.state != "ready":
                raise ValueError("请等待语音就绪，或先打断当前指令")
            started = time.monotonic()
            # Cloud frames have no turn IDs. Retire the previous connection before
            # accepting another local turn so late cloud tools cannot execute it.
            if self.cloud:
                self.generation += 1
                await super().disconnect()
            if self.watchdog is None:
                self.watchdog = asyncio.create_task(self._watch())
            self.started = self.last_activity = started
            self.turn = self.diagnostics.next_turn()
            self.frames = []
            self.uplink_frames = self.downlink_frames = 0
            self.state, self.route, self.error = "listening", "local_recording", ""
            self.record("listen_start", mode="local_first")
            await self.publish_status()
        elif self.state == "listening":
            self.state, self.route = "thinking", "local_recognizing"
            self.last_activity = time.monotonic()
            self.record("listen_stop")
            pcm = b"".join(self.frames)
            self.frames = []
            await self.publish_status()
            self.processing = asyncio.create_task(self._process(pcm, self.generation))

    async def audio(self, pcm):
        if self.pending_input is not None:
            return await super().audio(pcm)
        if self.state != "listening":
            return
        if len(pcm) != 1920:
            raise ValueError("音频帧必须是 16kHz / 60ms / PCM16 单声道")
        if len(self.frames) >= 250 or time.monotonic() - self.started >= RECORDING_LIMIT:
            await self.listen(False)
            return
        self.frames.append(pcm)

    async def _local_text(self, text, role="assistant"):
        await self.send({"type": "transcript", "role": role, "source": "local",
                         "text": redact_transcript(text, self.sensitive_values),
                         "generation": self.generation})

    async def _route(self, route, reason=None, **measurements):
        self.route = route
        self.record("voice_route", route=route, reason=reason, **measurements)
        await self.send({"type": "voice_route", "route": route, "reason": reason,
                         "generation": self.generation, **measurements})
        await self.publish_status()

    async def _process(self, pcm, generation):
        executed = False
        active = None
        try:
            if not pcm:
                await self._route("no_speech", "no_speech")
                await self._local_done("没有收到录音，请重新按住说话。", success=False)
                return
            try:
                result = await asr_client.recognize(pcm)
            except (httpx.TimeoutException, TimeoutError):
                await self._fallback(pcm, "asr_timeout")
                return
            except (httpx.HTTPError, ValueError):
                await self._fallback(pcm, "asr_unavailable")
                return
            if generation != self.generation:
                return
            self.record("local_asr", asr_ms=result["asr_ms"])
            text = result["text"]
            self.record("stt", text=text, text_chars=len(text), source="local",
                        sensitive_values=self.sensitive_values)
            await self._local_text(text, "user")
            if not result["speech"] and not text.strip():
                await self._route("no_speech", "no_speech")
                await self._local_done("没有识别到清晰语音，请再说一次。", success=False)
                return
            backend = self.motion.backend
            plan = parse_commands(text, physical=backend.kind == "mujoco",
                                  scene=getattr(backend, "scene", None))
            if not plan.actions:
                await self._fallback(pcm, plan.reason)
                return
            # Parsing and context checks cover the whole utterance before any action.
            await self._route("local", "matched", asr_ms=result["asr_ms"])
            for action in plan.actions:
                if generation != self.generation:
                    return
                record = await self.motion.submit(action)
                executed = True
                tool = "duck_set_scene" if action.name.startswith("scene_") else TOOLS.get(
                    action.name, "duck_" + action.name
                )
                call = self.diagnostics.sequence + 1
                self.record("action_start", call=call, tool=tool)
                active = (record["id"], call, tool)
                finished = await self.motion.wait(record["id"])
                self.last_activity = time.monotonic()
                self.record("action_end", call=call, tool=tool, result=finished["status"])
                active = None
                if finished["status"] != "completed":
                    await self._local_done(
                        "本地动作未完成：已取消或未通过验证，请查看动作日志。",
                        success=False,
                    )
                    return
            names = " → ".join(ALIASES[a.name].split("|")[0] for a in plan.actions)
            await self._local_done("本地已完成：" + names, success=True)
        except asyncio.CancelledError:
            if active:
                await self._stop_motion()
                finished = await self.motion.wait(active[0])
                self.record("action_end", call=active[1], tool=active[2], result=finished["status"])
            raise
        except Exception:
            if executed:
                await self._stop_motion()
            if generation == self.generation:
                await self._local_done("本地处理未完成，请重试。", success=False)

    async def _local_done(self, text, *, success):
        self.record("local_end", result="ok" if success else "error")
        await self._local_text(text)
        self.state = "ready"
        self.last_activity = time.monotonic()
        await self.publish_status()

    async def _fallback(self, pcm, reason):
        # Only reached before submitting a local action. Keep the same diagnostic
        # turn and original recording; never re-record or retry the upload.
        await self._route("cloud_fallback", reason)
        if self.watchdog and self.watchdog is not asyncio.current_task():
            self.watchdog.cancel()
            await asyncio.gather(self.watchdog, return_exceptions=True)
            self.watchdog = None
        try:
            self.mcp = DeviceMCP(self.motion, uuid.uuid4().hex[:12])
            async with asyncio.timeout(35):
                await self._open_transport(publish_ready=False)
            if self.state != "ready":
                return
            self.state = "thinking"
            await self._json({"session_id": self.session_id, "type": "listen",
                              "state": "start", "mode": "manual"})
            for offset in range(0, len(pcm), 1920):
                frame = pcm[offset:offset + 1920]
                await asyncio.wait_for(self.cloud.send(self.encoder.encode(frame)), IO_TIMEOUT)
                self.uplink_frames += 1
                if self.uplink_frames == 1:
                    self.record("uplink_first_frame")
            await self._json({"session_id": self.session_id, "type": "listen",
                              "state": "stop", "mode": "manual"})
            self.last_activity = time.monotonic()
            await self.publish_status()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.command_failed(exc)

    async def _interrupt(self):
        try:
            await self.send({"type": "playback_end", "aborted": True,
                             "generation": self.generation})
            await self.publish_status()
            await self.disconnect(discard_input=False)
            self.state = "ready"
            self.watchdog = asyncio.create_task(self._watch())
            pending = self.pending_input
            if not pending or not pending["started"]:
                self.pending_input = None
                await self.publish_status()
                return
            await self.listen(True, from_interrupt=True)
            self.started = pending["started"]
            self.frames = pending["frames"]
            self.pending_input = None
            if pending["stopped"]:
                await self.listen(False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.command_failed(exc)

    async def disconnect(self, *, discard_input=True):
        processing, self.processing = self.processing, None
        active = processing is not None and not processing.done()
        if processing and processing is not asyncio.current_task():
            processing.cancel()
            await asyncio.gather(processing, return_exceptions=True)
        self.frames = []
        await super().disconnect(discard_input=discard_input)
        if active:
            await self._stop_motion()
