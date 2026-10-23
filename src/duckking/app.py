"""Loopback HTTP/WebSocket application. No cloud account is needed for preview."""

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .motion import Action, MotionController, PreviewBackend

ROOT = Path(__file__).resolve().parents[2]


def same_origin(origin: str | None, host: str) -> bool:
    return origin is None or origin in {f"http://{host}", f"https://{host}"}


def create_app(controller: MotionController | None = None) -> FastAPI:
    motion = controller or MotionController(PreviewBackend())

    @asynccontextmanager
    async def lifespan(app):
        yield
        await motion.close()

    app = FastAPI(title="DuckKing", lifespan=lifespan)
    app.state.motion = motion
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

    @app.post("/api/actions", status_code=202)
    async def action(body: Action):
        try:
            return await motion.submit(body)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/actions/{request_id}")
    async def action_result(request_id: str):
        if request_id not in motion.records:
            raise HTTPException(404, "未知动作")
        return motion.records[request_id]

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
    args = parser.parse_args()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
