"""Loopback HTTP/WebSocket application. No cloud account is needed for preview."""

import argparse
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .diagnostics import VoiceDiagnostics
from .motion import Action, MotionController, PreviewBackend
from .robotd import RobotdBackend
from .voice import VoiceSession

ROOT = Path(__file__).resolve().parents[2]


def same_origin(origin: str | None, host: str) -> bool:
    return origin is None or origin in {f"http://{host}", f"https://{host}"}


def create_app(
    controller: MotionController | None = None, settings: Settings | None = None
) -> FastAPI:
    motion = controller or MotionController(PreviewBackend())

    @asynccontextmanager
    async def lifespan(app):
        yield
        if app.state.voice:
            await app.state.voice.disconnect()
        await motion.close()
        if app.state.scene_motion:
            await app.state.scene_motion.close()

    app = FastAPI(title="DuckKing", lifespan=lifespan)
    app.state.motion = motion
    app.state.voice = None
    app.state.scene_motion = None
    scene_lock = asyncio.Lock()
    app.state.voice_diagnostics = VoiceDiagnostics(
        (settings or Settings.load()).data_dir / "voice.jsonl"
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
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
        return {"ok": True, "version": "0.1.0", "backend": motion.backend.kind}

    @app.get("/api/state")
    async def state():
        return await motion.snapshot()

    @app.get("/api/voice/diagnostics")
    async def voice_diagnostics(request: Request):
        if not same_origin(request.headers.get("origin"), request.headers.get("host", "")):
            raise HTTPException(403, "仅允许同源本地操作")
        session = app.state.voice
        status = session.diagnostic_status() if session else {"state": "disconnected"}
        return JSONResponse(
            {**status, **app.state.voice_diagnostics.snapshot()},
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/actions", status_code=202)
    async def action(body: Action):
        try:
            return await motion.submit(body)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/voice/statistics")
    async def voice_statistics(request: Request, backend: str = "all"):
        if not same_origin(request.headers.get("origin"), request.headers.get("host", "")):
            raise HTTPException(403, "仅允许同源本地操作")
        if backend not in {"all", "preview", "robotd", "mujoco"}:
            raise HTTPException(422, "未知后端")
        journal = app.state.voice_diagnostics
        return JSONResponse(
            {
                **journal.statistics.snapshot(None if backend == "all" else backend),
                "storage_ok": journal.storage_ok,
                "current_backend": motion.backend.kind,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/actions/{request_id}")
    async def action_result(request_id: str):
        if request_id not in motion.records:
            raise HTTPException(404, "未知动作")
        return motion.records[request_id]

    def scene_controller():
        if app.state.scene_motion is None:
            raise HTTPException(503, "请先启动物理场景")
        return app.state.scene_motion

    @app.post("/api/scenes/start", status_code=202)
    async def start_scene(body: Action):
        if body.name not in {"scene_ball", "scene_duo"} or body.target != "a":
            raise HTTPException(422, "选择单鸭踢球或双鸭互动场景")
        async with scene_lock:
            if app.state.scene_motion is None:
                try:
                    from .simulation import MuJoCoBackend

                    assets = Path(os.environ.get("DUCKKING_SIM_DIR", ROOT / "external"))
                    backend = await asyncio.to_thread(MuJoCoBackend, assets)
                    app.state.scene_motion = MotionController(backend)
                except Exception as exc:
                    raise HTTPException(
                        503, "物理场景未就绪，请运行 scripts/setup_scenarios.sh 并重新启动服务"
                    ) from exc
            try:
                return await scene_controller().submit(body)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/api/scenes/model")
    async def scene_model():
        return JSONResponse(
            scene_controller().backend.geometry(), headers={"Cache-Control": "no-store"}
        )

    @app.get("/api/scenes/state")
    async def scene_state():
        return await scene_controller().snapshot()

    @app.post("/api/scenes/actions", status_code=202)
    async def scene_action(body: Action):
        try:
            return await scene_controller().submit(body)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/scenes/actions/{request_id}")
    async def scene_result(request_id: str):
        controller = scene_controller()
        if request_id not in controller.records:
            raise HTTPException(404, "未知场景动作")
        return controller.records[request_id]

    @app.websocket("/scene-ws")
    async def scene_stream(ws: WebSocket):
        if not same_origin(ws.headers.get("origin"), ws.headers.get("host", "")):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            while True:
                controller = app.state.scene_motion
                await ws.send_json(
                    {"type": "state", **await controller.snapshot()}
                    if controller
                    else {"type": "not_started"}
                )
                await asyncio.sleep(0.05)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass

    @app.websocket("/ws")
    async def state_stream(ws: WebSocket):
        if not same_origin(ws.headers.get("origin"), ws.headers.get("host", "")):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            while True:
                await ws.send_text(json.dumps({"type": "state", **await motion.snapshot()}))
                await asyncio.sleep(0.05)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass

    @app.websocket("/voice")
    @app.websocket("/scene-voice")
    async def voice_stream(ws: WebSocket):
        if not same_origin(ws.headers.get("origin"), ws.headers.get("host", "")):
            await ws.close(code=1008)
            return
        if app.state.voice is not None:
            await ws.accept()
            await ws.send_json(
                {
                    "type": "voice_status",
                    "state": "busy",
                    "error": "另一个页面正在使用语音，请先在该页面断开",
                }
            )
            await ws.close(code=1008)
            return
        await ws.accept()
        voice_motion = app.state.scene_motion if ws.url.path == "/scene-voice" else motion
        if voice_motion is None:
            await ws.send_json(
                {"type": "voice_status", "state": "error", "error": "请先启动物理场景再连接灵矽"}
            )
            await ws.close(code=1008)
            return
        session = VoiceSession(
            ws.send_json, voice_motion, settings or Settings.load(), app.state.voice_diagnostics
        )
        app.state.voice = session
        try:
            await session.publish_status()
            while True:
                message = await ws.receive()
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
                        await session.disconnect()
                        await session.publish_status()
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
            await session.disconnect()
            app.state.voice = None

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
    parser.add_argument("--backend", choices=["preview", "robotd"], default="preview")
    parser.add_argument("--socket", default="~/.cache/duck-sim/duck-a.sock")
    args = parser.parse_args()
    backend = PreviewBackend() if args.backend == "preview" else RobotdBackend(args.socket)
    uvicorn.run(create_app(MotionController(backend)), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
