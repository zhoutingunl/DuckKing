"""Loopback HTTP/WebSocket application. No cloud account is needed for preview."""

import argparse
import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import anyio
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import asr_client
from .config import Settings
from .deployment import DeploymentStatus
from .diagnostics import VoiceDiagnostics
from .experience import ExperienceBatch, ExperienceContext, ExperienceStore, VoiceExperience
from .hybrid_voice import HybridVoiceSession
from .model_metrics import ModelLoadMetrics
from .motion import Action, MotionController, PreviewBackend
from .robotd import RobotdBackend
from .rooms import RoomRegistry
from .studio import CATALOG, Studio
from .voice import VoiceSession
from .voice_profiles import public_profiles

ROOT = Path(__file__).resolve().parents[2]
SCENE_STATE_ACK_TIMEOUT = 30
VOICE_BROWSER_IDLE_TIMEOUT = 45


def same_origin(origin: str | None, host: str) -> bool:
    return origin is None or origin in {f"http://{host}", f"https://{host}"}


def create_app(
    controller: MotionController | None = None,
    settings: Settings | None = None,
    allowed_hosts: list[str] | None = None,
) -> FastAPI:
    motion = controller or MotionController(PreviewBackend())

    @asynccontextmanager
    async def lifespan(app):
        reaper = asyncio.create_task(app.state.room_registry.watch())
        try:
            yield
        finally:
            reaper.cancel()
            await asyncio.gather(reaper, return_exceptions=True)
            for room in list(app.state.rooms.values()):
                if room.voice:
                    await room.voice.disconnect()
                await room.motion.close()
                if room.scene_motion:
                    await room.scene_motion.close()
            await anyio.to_thread.run_sync(app.state.experience.close)

    app = FastAPI(title="DuckKing", lifespan=lifespan)
    app.state.motion = motion
    app.state.voice = None
    app.state.scene_motion = None
    app.state.deployment = DeploymentStatus(
        Path(os.getenv("DUCKKING_RELEASE_FILE", ROOT / "release.json")),
        Path(
            os.getenv(
                "DUCKKING_DEPLOY_HISTORY",
                (settings or Settings.load()).data_dir / "deployments.jsonl",
            )
        ),
    )
    app.state.settings = settings or Settings.load()
    app.state.experience = ExperienceStore(
        app.state.settings.data_dir / "experience.sqlite3",
        (app.state.deployment.release or {}).get("commit", "development"),
    )
    app.state.scene_lock = asyncio.Lock()
    app.state.viewers = 0
    app.state.reserved_until = 0.0
    app.state.voice_diagnostics = VoiceDiagnostics(
        (settings or Settings.load()).data_dir / "voice.jsonl",
        experience=VoiceExperience(app.state.experience, "1"),
    )
    app.state.room_registry = RoomRegistry(app.state)
    app.state.rooms = app.state.room_registry.rooms
    app.state.physics_lock = asyncio.Lock()

    def get_room(number="1"):
        return app.state.room_registry.get(number)

    async def socket_room(ws):
        # Selection is a protocol frame so existing HTTPS bridges need no changes.
        # Explicit query selection also supports local protocol clients.
        if not same_origin(ws.headers.get("origin"), ws.headers.get("host", "")):
            if ws.url.path.endswith("/scene-ws"):
                logging.getLogger(__name__).warning("scene_ws_rejected: origin_mismatch")
            await ws.close(code=1008)
            return None
        await ws.accept()
        try:
            number = ws.query_params.get("room")
            if number is None:
                data = await asyncio.wait_for(ws.receive_json(), 5)
                if not isinstance(data, dict) or data.get("type") != "join_room":
                    raise ValueError("room required")
                number = data.get("room")
            if number not in app.state.rooms:
                raise ValueError("invalid room")
            return get_room(number)
        except (ValueError, TypeError, TimeoutError, WebSocketDisconnect):
            with suppress(RuntimeError, OSError):
                await ws.close(code=1008)
            return None

    @app.get("/api/rooms")
    async def rooms():
        return JSONResponse(app.state.room_registry.snapshot(),
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/rooms/claim")
    async def claim_room():
        return await app.state.room_registry.claim()

    @app.post("/api/rooms", status_code=201)
    async def create_room():
        return await app.state.room_registry.claim(create=True)

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts or ["localhost", "127.0.0.1", "testserver"],
    )

    @app.middleware("http")
    async def protect_local_mutations(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(
            request.headers.get("origin"), request.headers.get("host", "")
        ):
            return JSONResponse({"detail": "仅允许同源本地操作"}, status_code=403)
        return await call_next(request)

    @app.get("/api/health")
    async def health():
        return {
            "ok": True,
            "version": "0.1.0",
            "backend": motion.backend.kind,
            "release": app.state.deployment.release or None,
        }

    @app.get("/api/deployments")
    async def deployments():
        return JSONResponse(app.state.deployment.snapshot(), headers={"Cache-Control": "no-store"})

    @app.post("/api/experience", status_code=202)
    async def experience_ingest(request: Request, room: str = "1"):
        # Bound streamed bodies too; Content-Length is not trusted.
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 32768:
                raise HTTPException(413, "统计批次过大")
        if not re.fullmatch(r"[1-9][0-9]?", room):
            raise HTTPException(422, "无效统计房间")
        try:
            batch = ExperienceBatch.model_validate_json(body)
        except ValueError as exc:
            raise HTTPException(422, "统计格式无效") from exc
        accepted = sum(app.state.experience.submit(e, source="browser", room=room)
                       for e in batch.events)
        if accepted != len(batch.events):
            raise HTTPException(503, "统计队列已满，请稍后重试")
        return {"queued": accepted}

    @app.get("/api/experience")
    async def experience_summary(
        hours: int = 168,
        traffic: str = "interactive",
        page: str = "all",
        device: str = "all",
        cache: str = "all",
        room: str = "all",
        release: str = "all",
        backend: str = "all",
        scene: str = "all",
    ):
        allowed = {
            "traffic": {"all", "interactive", "demo", "verification", "unattributed"},
            "page": {"all", "home", "scenarios", "demos", "studio", "unknown"},
            "device": {"all", "mobile", "desktop", "unknown"},
            "cache": {"all", "network", "http", "persistent", "memory", "unknown"},
            "backend": {"all", "preview", "mujoco", "robotd", "unknown"},
            "scene": {
                "all",
                "ball",
                "duo",
                "carry",
                "skills",
                "rollers",
                "table",
                "seated",
                "stage",
                "unknown",
            },
        }
        filters = dict(
            traffic=traffic, page=page, device=device, cache=cache, backend=backend, scene=scene
        )
        if (
            hours not in {1, 24, 168, 720, 2160}
            or any(v not in allowed[k] for k, v in filters.items())
            or (room != "all" and not re.fullmatch(r"[1-9][0-9]?", room))
            or (
                release not in {"all", "development"} and not re.fullmatch(r"[a-f0-9]{40}", release)
            )
        ):
            raise HTTPException(422, "未知统计筛选")
        result = await anyio.to_thread.run_sync(lambda: app.state.experience.snapshot(
            hours=hours, room=room, release=release, **filters))
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    async def state(room: str = "1"):
        return await get_room(room).motion.snapshot()

    @app.get("/api/voice/diagnostics")
    async def voice_diagnostics(request: Request, room: str = "1"):
        if not same_origin(request.headers.get("origin"), request.headers.get("host", "")):
            raise HTTPException(403, "仅允许同源本地操作")
        selected = get_room(room)
        session = selected.voice
        status = session.diagnostic_status() if session else {"state": "disconnected"}
        return JSONResponse(
            {**status, **selected.voice_diagnostics.snapshot()},
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/actions", status_code=202)
    async def action(body: Action, room: str = "1"):
        try:
            return await get_room(room).motion.submit(body)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/voice/statistics")
    async def voice_statistics(request: Request, backend: str = "all", room: str = "1"):
        if not same_origin(request.headers.get("origin"), request.headers.get("host", "")):
            raise HTTPException(403, "仅允许同源本地操作")
        if backend not in {"all", "preview", "robotd", "mujoco"}:
            raise HTTPException(422, "未知后端")
        journal = get_room(room).voice_diagnostics
        return JSONResponse(
            {
                **journal.statistics.snapshot(None if backend == "all" else backend),
                "storage_ok": journal.storage_ok,
                "current_backend": get_room(room).motion.backend.kind,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/actions/{request_id}")
    async def action_result(request_id: str, room: str = "1"):
        motion = get_room(room).motion
        if request_id not in motion.records:
            raise HTTPException(404, "未知动作")
        return motion.records[request_id]

    def scene_controller(room="1"):
        selected = get_room(room)
        if selected.scene_motion is None:
            raise HTTPException(503, "请先启动物理场景")
        return selected.scene_motion

    @app.post("/api/scenes/start", status_code=202)
    async def start_scene(body: Action, room: str = "1"):
        if (
            body.name
            not in {
                "scene_ball",
                "scene_duo",
                "scene_carry",
                "scene_table",
                "scene_seated",
                "scene_skills",
                "scene_rollers",
                "scene_stage",
            }
            or body.target != "a"
        ):
            raise HTTPException(422, "请选择有效的物理场景")
        selected = get_room(room)
        async with selected.scene_lock:
            if selected.scene_motion is None:
                async with app.state.physics_lock:
                    count = sum(r.scene_motion is not None for r in app.state.rooms.values())
                    limit = app.state.room_registry.physics_limit
                    if count >= limit:
                        raise HTTPException(
                            409, f"物理场景已达并发上限（{limit}）；"
                            "请释放空闲场景后重试，语音工作台仍可使用",
                        )
                    try:
                        from .simulation import MuJoCoBackend

                        assets = Path(os.environ.get("DUCKKING_SIM_DIR", ROOT / "external"))
                        backend = await asyncio.to_thread(MuJoCoBackend, assets)
                        selected.scene_motion = MotionController(backend)
                        selected.scene_motion.studio = Studio(
                            selected.scene_motion, selected.settings.data_dir
                        )
                    except Exception as exc:
                        raise HTTPException(
                            503, "物理场景未就绪，请运行 scripts/setup_scenarios.sh 并重新启动服务"
                        ) from exc
            try:
                return await scene_controller(room).submit(body)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/api/studio")
    async def studio_status(room: str = "1"):
        return scene_controller(room).studio.snapshot()

    @app.post("/api/studio/select")
    async def studio_select(body: dict, room: str = "1"):
        selected = get_room(room)
        if selected.voice is not None:
            raise HTTPException(409, "请先断开语音再切换节目")
        scene = body.get("scene")
        if not isinstance(scene, str) or scene not in CATALOG:
            raise HTTPException(422, "未知互动节目")
        controller = scene_controller(room)
        if controller.backend.scene != CATALOG[scene][1]:
            raise HTTPException(409, "请先准备对应的物理舞台")
        return await controller.studio.select(scene)

    @app.post("/api/studio/action")
    async def studio_action(body: dict, room: str = "1"):
        try:
            studio = scene_controller(room).studio
            if "rehearsal_text" in body:
                text = body["rehearsal_text"]
                if not isinstance(text, str) or len(text) > 1000:
                    raise ValueError("排练文本长度超限")
                studio.heard(text)
            return await studio.invoke(
                body.get("name"), body.get("arguments", {}), wait=False, manual=True)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/scenes/close", status_code=204)
    async def close_scene(room: str = "1", if_unused: bool = False):
        selected = get_room(room)
        async with selected.scene_lock:
            if if_unused and app.state.room_registry.busy(selected):
                raise HTTPException(409, "房间仍有人使用，保留物理场景")
            if selected.voice is not None:
                raise HTTPException(409, "请先断开本房间语音，再释放物理场景")
            controller, selected.scene_motion = selected.scene_motion, None
            if controller:
                await controller.close()
        return Response(status_code=204)

    @app.get("/api/models/microduck")
    async def preview_model():
        try:
            from .model_assets import official_preview

            assets = Path(os.environ.get("DUCKKING_SIM_DIR", ROOT / "external"))
            model = await asyncio.to_thread(official_preview, assets)
        except Exception as exc:
            raise HTTPException(
                503, "官方外观模型未就绪，请运行 scripts/setup_scenarios.sh 并重启服务"
            ) from exc
        return JSONResponse(model, headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/api/scenes/model")
    async def scene_model(room: str = "1"):
        return JSONResponse(
            scene_controller(room).backend.geometry(), headers={"Cache-Control": "no-store"}
        )

    @app.get("/api/scenes/model.dkm.gz")
    async def compressed_scene_model(room: str = "1"):
        started = time.perf_counter()
        # Export current physics geometry; compression never steps or modifies physics.
        backend = scene_controller(room).backend
        import gzip

        from .model_assets import pack_visual_model

        if not hasattr(backend, "packed_visual_cache"):
            backend.packed_visual_cache = {}
        key = backend.revision
        if key not in backend.packed_visual_cache:
            model = {**backend.geometry(), "source": "official_microduck_physics", "physics": True}
            backend.packed_visual_cache[key] = await asyncio.to_thread(
                lambda: gzip.compress(pack_visual_model(model), compresslevel=6, mtime=0)
            )
        prepared_ms = (time.perf_counter() - started) * 1000
        return Response(backend.packed_visual_cache[key], media_type="application/octet-stream",
                        headers={"Content-Encoding": "gzip", "Cache-Control": "no-store",
                                 "Server-Timing": f"model_prepare;dur={prepared_ms:.1f}"})

    async def load_visual_asset():
        try:
            from .model_assets import visual_asset

            assets = Path(os.environ.get("DUCKKING_SIM_DIR", ROOT / "external"))
            return await asyncio.to_thread(visual_asset, assets)
        except Exception as exc:
            raise HTTPException(
                503, "官方外观模型未就绪，请运行 scripts/setup_scenarios.sh 并重启服务"
            ) from exc

    @app.get("/api/models/microduck/manifest")
    async def visual_manifest(request: Request):
        started = time.perf_counter()
        asset = await load_visual_asset()
        headers = {
            "Cache-Control": "no-cache", "ETag": f'"{asset.version}"',
            "Server-Timing": f"model_prepare;dur={(time.perf_counter() - started) * 1000:.1f}",
        }
        if request.headers.get("if-none-match") == headers["ETag"]:
            return Response(status_code=304, headers=headers)
        return JSONResponse(asset.manifest(), headers=headers)

    @app.get("/api/models/microduck/assets/{version}.dkm.gz")
    async def visual_mesh(version: str, request: Request):
        if not re.fullmatch(r"[a-f0-9]{64}", version):
            raise HTTPException(404, "未知模型版本")
        asset = await load_visual_asset()
        if version != asset.version:
            raise HTTPException(404, "模型版本已更新，请刷新页面")
        headers = {"Cache-Control": "public, max-age=31536000, immutable", "ETag": f'"{version}"'}
        if request.headers.get("if-none-match") == headers["ETag"]:
            return Response(status_code=304, headers=headers)
        # This explicit .gz representation is always gzip. The HTTPS bridge
        # sends Accept-Encoding: identity but forwards encoded bytes unchanged.
        return Response(asset.compressed, media_type="application/octet-stream",
                        headers={**headers, "Content-Encoding": "gzip"})

    @app.post("/api/models/load-metrics", status_code=204)
    async def model_load_metrics(request: Request, room: str = "1"):
        get_room(room)
        try:
            body = ModelLoadMetrics.model_validate(await request.json())
        except ValueError as exc:
            raise HTTPException(422, "模型加载耗时格式无效") from exc
        logging.getLogger("uvicorn.error").info(
            "official_model_load source=browser_reported room=%s %s", room, body.model_dump_json()
        )
        return Response(status_code=204)

    @app.post("/api/scenes/stage/selection")
    async def stage_selection(request: Request, room: str = "1"):
        from .stage import StageSelection

        try:
            selection = StageSelection.model_validate(await request.json())
            backend = scene_controller(room).backend
            if not backend.stage:
                raise ValueError("请先准备四鸭发布会舞台")
            return backend.stage.select(selection)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, "点选无效或舞台已重置，请重新点选") from exc

    @app.get("/api/scenes/state")
    async def scene_state(room: str = "1"):
        return await scene_controller(room).snapshot()

    @app.post("/api/scenes/actions", status_code=202)
    async def scene_action(body: Action, room: str = "1"):
        try:
            return await scene_controller(room).submit(body)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/scenes/actions/{request_id}")
    async def scene_result(request_id: str, room: str = "1"):
        controller = scene_controller(room)
        if request_id not in controller.records:
            raise HTTPException(404, "未知场景动作")
        return controller.records[request_id]

    @app.websocket("/scene-ws")
    async def scene_stream(ws: WebSocket):
        room = await socket_room(ws)
        if room is None:
            return
        room.viewers += 1
        room.reserved_until = 0
        try:
            while True:
                controller = room.scene_motion
                await ws.send_json(
                    {"type": "state", **await controller.snapshot()}
                    if controller
                    else {"type": "not_started"}
                )
                # One outstanding snapshot: a slow renderer must receive current
                # physics, not an ever-growing queue of obsolete frames.
                message = await asyncio.wait_for(ws.receive(), timeout=SCENE_STATE_ACK_TIMEOUT)
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("text") != "next":
                    await ws.close(code=1008)
                    return
                await asyncio.sleep(0.05)
        except TimeoutError:
            logging.getLogger(__name__).warning("scene_ws_closed: acknowledgement_timeout")
            await ws.close(code=1001)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
        finally:
            room.viewers -= 1
            room.last_used = time.monotonic()

    @app.websocket("/ws")
    async def state_stream(ws: WebSocket):
        room = await socket_room(ws)
        if room is None:
            return
        room.viewers += 1
        room.reserved_until = 0
        try:
            while True:
                await ws.send_text(json.dumps({"type": "state", **await room.motion.snapshot()}))
                await asyncio.sleep(0.05)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
        finally:
            room.viewers -= 1
            room.last_used = time.monotonic()

    @app.get("/api/voice/profiles")
    async def voice_profiles(room: str = "1"):
        return public_profiles(get_room(room).settings)

    @app.get("/api/voice/modes")
    async def voice_modes():
        configured = app.state.settings.local_asr
        status = await asr_client.availability() if configured else {"available": False}
        return {"local_first": configured, **status}

    @app.websocket("/voice")
    @app.websocket("/scene-voice")
    async def voice_stream(ws: WebSocket):
        room = await socket_room(ws)
        if room is None:
            return
        if room.voice is not None:
            await ws.send_json(
                {
                    "type": "voice_status",
                    "state": "busy",
                    "error": "本房间的语音正在使用，请选择另一个房间或在原页面断开",
                }
            )
            await ws.close(code=1008)
            return
        voice_motion = room.scene_motion if ws.url.path.endswith("/scene-voice") else room.motion
        if voice_motion is None:
            await ws.send_json(
                {"type": "voice_status", "state": "error", "error": "请先加载物理场景，再启用语音"}
            )
            await ws.close(code=1008)
            return
        finished = asyncio.Event()
        initial_status = True

        async def send_voice(message):
            nonlocal initial_status
            await ws.send_json(message)
            if message.get("type") == "voice_status":
                if not initial_status and message.get("state") in {"error", "disconnected"}:
                    finished.set()
                initial_status = False

        session = VoiceSession(
            send_voice, voice_motion, room.settings, room.voice_diagnostics
        )
        # Reserve without yielding after room selection. Each room has its own device.
        room.voice = session
        receiver = None
        terminal = asyncio.create_task(finished.wait())
        manual_disconnect = False
        try:
            await session.publish_status()
            while True:
                receiver = asyncio.create_task(ws.receive())
                done, _ = await asyncio.wait(
                    {receiver, terminal}, timeout=VOICE_BROWSER_IDLE_TIMEOUT,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    session.record("timeout", reason="browser_idle")
                    break
                if terminal in done:
                    break
                message = receiver.result()
                if message["type"] == "websocket.disconnect":
                    break
                try:
                    if message.get("bytes") is not None:
                        await session.audio(message["bytes"])
                        continue
                    data = json.loads(message.get("text") or "{}")
                    if not isinstance(data, dict):
                        raise ValueError("语音指令必须为 JSON 对象")
                    command = data.get("type")
                    if command == "connect":
                        mode = data.get("mode", "cloud")
                        if mode not in {"cloud", "local_first"}:
                            raise ValueError("未知语音模式")
                        if (mode == "local_first" and voice_motion.studio
                                and voice_motion.studio.active):
                            raise ValueError("现场互动节目使用灵矽理解，请选择灵矽模式")
                        if mode == "local_first" and not isinstance(session, HybridVoiceSession):
                            if not room.settings.local_asr:
                                raise ValueError("服务器尚未启用本地识别")
                            if session.state != "disconnected":
                                raise ValueError("请先断开语音，再切换模式")
                            session = HybridVoiceSession(
                                send_voice, voice_motion, room.settings, room.voice_diagnostics
                            )
                            room.voice = session
                        if mode == "cloud" and isinstance(session, HybridVoiceSession):
                            raise ValueError("请先断开语音，再切换模式")
                        session.start_connect()
                    elif command == "voice_style":
                        await session.set_style(data.get("settings", {}))
                    elif command == "persona":
                        session.set_persona(data.get("settings", {}))
                    elif command == "listen_start":
                        try:
                            room.voice_diagnostics.experience.pending = (
                                ExperienceContext.model_validate(data["experience"])
                                if "experience" in data else None)
                            if room.voice_diagnostics.experience.pending:
                                room.voice_diagnostics.experience.pending.scene = getattr(
                                    voice_motion.backend, "scene", "unknown")
                        except (ValueError, TypeError):
                            room.voice_diagnostics.experience.pending = None
                        await session.listen(True)
                    elif command == "listen_stop":
                        await session.listen(False)
                    elif command == "disconnect":
                        manual_disconnect = True
                        break
                    elif command == "ping":
                        await ws.send_json({"type": "pong"})
                    elif command == "playback_status":
                        room.voice_diagnostics.update_playback(data)
                    elif command == "interrupt":
                        session.start_interrupt()
                    elif command == "reset":
                        await session.reset(manual=True)
                    else:
                        raise ValueError("未知语音指令")
                except ValueError as exc:
                    await ws.send_json({"type": "error", "message": str(exc)})
                except (WebSocketDisconnect, RuntimeError):
                    # A browser closing during status delivery is not a failed cloud command.
                    raise
                except Exception as exc:
                    await session.command_failed(exc)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
        finally:
            # ASGI cancellation must not interrupt cleanup and leave the device
            # reserved. Cloud shutdown itself retains its existing IO timeout.
            with anyio.CancelScope(shield=True):
                pending = [task for task in (receiver, terminal) if task is not None]
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                try:
                    await session.disconnect()
                finally:
                    if room.voice is session:
                        room.voice = None
                        room.last_used = time.monotonic()
                    with suppress(WebSocketDisconnect, RuntimeError, OSError):
                        if manual_disconnect:
                            session.activation_code = session.error = ""
                            await session.publish_status()
                        await ws.close(code=1000)

    static = ROOT / "frontend" / "dist"
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="frontend")
    else:

        @app.get("/")
        async def missing_frontend():
            return JSONResponse({"detail": "先执行 cd frontend && npm ci && npm run build"}, 503)

    return app


def main():
    parser = argparse.ArgumentParser(description="DuckKing local workbench")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        help="Additional exact public hostname; no wildcard or port",
    )
    parser.add_argument("--root-path", default="", help="External proxy prefix, e.g. /duckking")
    parser.add_argument("--backend", choices=["preview", "robotd"], default="preview")
    parser.add_argument("--socket", default="~/.cache/duck-sim/duck-a.sock")
    args = parser.parse_args()
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host) for host in args.allowed_host):
        parser.error("--allowed-host requires an exact hostname without scheme, wildcard or port")
    if args.root_path and not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", args.root_path):
        parser.error("--root-path requires a path such as /duckking, without a trailing slash")
    backend = PreviewBackend() if args.backend == "preview" else RobotdBackend(args.socket)
    options = {"host": args.host, "port": args.port}
    if args.root_path:
        options["root_path"] = args.root_path
    hosts = ["localhost", "127.0.0.1", "testserver", *args.allowed_host]
    uvicorn.run(create_app(MotionController(backend), allowed_hosts=hosts), **options)


if __name__ == "__main__":
    main()
