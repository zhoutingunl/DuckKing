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
from types import SimpleNamespace

import anyio
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .deployment import DeploymentStatus
from .diagnostics import VoiceDiagnostics
from .model_metrics import ModelLoadMetrics
from .motion import Action, MotionController, PreviewBackend
from .robotd import RobotdBackend
from .voice import VoiceSession

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
        yield
        for room in app.state.rooms.values():
            if room.voice:
                await room.voice.disconnect()
            await room.motion.close()
            if room.scene_motion:
                await room.scene_motion.close()

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
    app.state.scene_lock = asyncio.Lock()
    app.state.viewers = 0
    app.state.reserved_until = 0.0
    app.state.voice_diagnostics = VoiceDiagnostics(
        (settings or Settings.load()).data_dir / "voice.jsonl"
    )
    second_settings = app.state.settings.for_room("2")
    app.state.rooms = {"1": app.state}
    if motion.backend.kind == "preview":
        app.state.rooms["2"] = SimpleNamespace(
            motion=MotionController(PreviewBackend()), voice=None, scene_motion=None,
            settings=second_settings, scene_lock=asyncio.Lock(), viewers=0, reserved_until=0.0,
            voice_diagnostics=VoiceDiagnostics(second_settings.data_dir / "voice.jsonl"),
        )

    def get_room(number="1"):
        if number not in app.state.rooms:
            raise HTTPException(404, "房间不存在或当前 robotd 后端不支持独立第二房间")
        return app.state.rooms[number]

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
        return {"rooms": [{"id": number, "viewers": room.viewers,
                           "voice_busy": room.voice is not None}
                          for number, room in app.state.rooms.items()]}

    @app.post("/api/rooms/claim")
    async def claim_room():
        # A short reservation prevents simultaneous page loads choosing one room.
        # Rooms are public demo spaces, not authenticated private accounts.
        for number, room in app.state.rooms.items():
            if not room.viewers and room.voice is None and room.reserved_until <= time.monotonic():
                room.reserved_until = time.monotonic() + 10
                return {"room": number}
        raise HTTPException(409, "两个房间均在使用，请选择房间查看；语音需要等待该房间释放")

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
        if body.name not in {"scene_ball", "scene_duo", "scene_carry"} or body.target != "a":
            raise HTTPException(422, "选择踢球、双鸭互动或嘴部搬运场景")
        selected = get_room(room)
        async with selected.scene_lock:
            if selected.scene_motion is None:
                try:
                    from .simulation import MuJoCoBackend

                    assets = Path(os.environ.get("DUCKKING_SIM_DIR", ROOT / "external"))
                    backend = await asyncio.to_thread(MuJoCoBackend, assets)
                    selected.scene_motion = MotionController(backend)
                except Exception as exc:
                    raise HTTPException(
                        503, "物理场景未就绪，请运行 scripts/setup_scenarios.sh 并重新启动服务"
                    ) from exc
            try:
                return await scene_controller(room).submit(body)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

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
        return Response(backend.packed_visual_cache[key], media_type="application/octet-stream",
                        headers={"Content-Encoding": "gzip", "Cache-Control": "no-store"})

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
                {"type": "voice_status", "state": "error", "error": "请先启动物理场景再连接灵矽"}
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
                        session.start_connect()
                    elif command == "listen_start":
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
