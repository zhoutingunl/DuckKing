"""Seesaw uses the existing room/model/WebSocket/voice transports."""

import asyncio
import os
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from .motion import MotionController


def install_seesaw_api(app, get_room, root):
    # Keep optional MuJoCo/numpy imports out of normal application startup.
    directory = Path(os.getenv("DUCKKING_SEESAW_ARTIFACTS", root / "training/seesaw_results"))
    assets = Path(os.getenv("DUCKKING_SIM_DIR", root / "external"))

    @app.get("/api/seesaw/training")
    async def training():
        import json

        try:
            data = await asyncio.to_thread((directory / "report.json").read_text)
            report = json.loads(data)
        except (OSError, ValueError):
            report = None
        return JSONResponse({"report": report}, headers={"Cache-Control": "no-store"})

    @app.post("/api/seesaw/prepare")
    async def prepare(room: str = "1", replace: bool = True):
        selected = get_room(room)
        async with selected.scene_lock:
            current = selected.scene_motion
            if current and getattr(current.backend, "scene", None) == "seesaw":
                return await current.snapshot()
            if current and not replace:
                raise HTTPException(409, {
                    "code": "scene_conflict",
                    "message": "本房间已有其他场景。点击“切换为跷跷板”会结束原场景；也可新建房间。",
                })
            if selected.voice:
                raise HTTPException(409, "请先断开当前房间语音，再切换物理世界")
            if current:
                await current.close()
                selected.scene_motion = None
            async with app.state.physics_lock:
                if sum(r.scene_motion is not None for r in app.state.rooms.values()) >= (
                    app.state.room_registry.physics_limit
                ):
                    raise HTTPException(409, "物理场景已达并发上限，请释放空闲场景")
                try:
                    from .seesaw_backend import SeesawArtifacts, SeesawBackend

                    backend = await asyncio.to_thread(
                        SeesawBackend, assets, SeesawArtifacts(directory)
                    )
                except Exception as exc:
                    raise HTTPException(
                        503, "跷跷板加载失败，请检查官方物理资源与服务器日志"
                    ) from exc
                selected.scene_motion = MotionController(backend)
            return await selected.scene_motion.snapshot()

    @app.post("/api/seesaw/command")
    async def command(body: dict, room: str = "1"):
        current = get_room(room).scene_motion
        if not current or getattr(current.backend, "scene", None) != "seesaw":
            raise HTTPException(409, "请先准备跷跷板场景")
        try:
            return await current.backend.invoke(body)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
