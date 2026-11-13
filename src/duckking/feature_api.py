"""Functional scenes share visitor rooms and the existing geometry/voice transports."""

import asyncio
import os
from contextlib import suppress
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from .feature_catalog import CATALOG, FeatureCommand
from .motion import MotionController
from .scene_discovery import SceneDiscovery, VisitEvent


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability: str
    replace: bool = False
    variant: Literal[10, 15, 20, 25, 50, 100, 140, 200] | None = None


def install_feature_api(app, get_room, root):
    assets = Path(os.environ.get("DUCKKING_SIM_DIR", root / "external"))
    app.state.discovery = SceneDiscovery(app.state.settings.data_dir / "scene-discovery.sqlite3")

    @app.get("/api/features/catalog")
    async def catalog(
        sort: str = Query("top", pattern="^(top|latest)$"),
    ):
        return await asyncio.to_thread(app.state.discovery.catalog, CATALOG, sort)

    @app.post("/api/features/visits", status_code=202)
    async def visit(body: VisitEvent, room: str = "1"):
        selected = get_room(room)
        try:
            await asyncio.to_thread(app.state.discovery.event, body, selected.lease, CATALOG)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"accepted": True}

    @app.get("/api/features/emotion-audio/{name}.wav")
    async def emotion_audio(name: str):
        if name not in CATALOG["emotions"]["commands"]:
            raise HTTPException(404, "没有这个情绪声音")
        # Two official emotions provide named variants rather than no.wav /
        # angry.wav. Serve one deterministic official variant for browser cache.
        sound = {"no": "no_a", "angry": "angry_a"}.get(name, name)
        file = assets / "features/emotions/sounds" / f"{sound}.wav"
        if not await asyncio.to_thread(file.is_file):
            raise HTTPException(503, "情绪声音资源尚未安装")
        return FileResponse(
            file, media_type="audio/wav", headers={"Cache-Control": "public,max-age=86400"}
        )

    @app.post("/api/features/prepare")
    async def prepare(body: Selection, room: str = "1"):
        if body.capability not in CATALOG:
            raise HTTPException(422, "未知功能场景")
        if body.variant is not None and body.capability != "stilts":
            raise HTTPException(422, "当前场景没有高跷高度设置")
        selected = get_room(room)
        async with selected.scene_lock:
            current = selected.scene_motion
            if (
                current
                and not body.replace
                and getattr(current.backend, "scene", None) == "functional"
                and current.backend.capability == body.capability
                and getattr(current.backend, "variant", None) == body.variant
                and not current.backend.error
                and not current.backend.closed
            ):
                return await current.snapshot()
            if current and not body.replace:
                raise HTTPException(
                    409, {"code": "scene_conflict", "message": "本房间已有场景，请切换或新建房间。"}
                )
            if selected.voice:
                raise HTTPException(409, "请先断开当前语音，再切换功能场景")
            if current:
                await current.close()
                selected.scene_motion = None
            selected.preparing = {"phase": "models", "completed": 0, "total": 1}
            try:
                async with app.state.physics_lock:
                    await app.state.warm_worlds.discard()
                    if sum(r.scene_motion is not None for r in app.state.rooms.values()) >= (
                        app.state.room_registry.physics_limit
                    ):
                        raise HTTPException(409, "物理场景已达并发上限，请释放空闲场景")
                    from .feature_backend import FeatureBackend

                    backend = None
                    try:
                        backend = await FeatureBackend.create(
                            assets,
                            body.capability,
                            **({"variant": body.variant} if body.variant is not None else {}),
                        )
                        selected.scene_motion = MotionController(backend)
                    except BaseException:
                        if backend:
                            with suppress(Exception):
                                await asyncio.shield(backend.close())
                        raise
            except ValueError as exc:
                raise HTTPException(503, str(exc)) from exc
            except TimeoutError as exc:
                raise HTTPException(503, "场景准备超时，物理进程已释放，请重新准备") from exc
            finally:
                selected.preparing = None
            return await selected.scene_motion.snapshot()

    @app.post("/api/features/command", status_code=202)
    async def command(body: FeatureCommand, room: str = "1"):
        current = get_room(room).scene_motion
        if current is None or getattr(current.backend, "scene", None) != "functional":
            raise HTTPException(409, "请先准备功能场景")
        try:
            return await current.backend.invoke(body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
