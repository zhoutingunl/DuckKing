"""Balance routes reuse existing room, model and voice transports (including HTTPS)."""

import asyncio
import os
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from .balance_runs import BalanceRuns
from .motion import MotionController


def install_balance_api(app, get_room, root):
    runs = BalanceRuns(
        os.getenv("DUCKKING_BALANCE_RUNS", app.state.settings.data_dir / "balance/runs"),
        os.getenv("DUCKKING_BALANCE_BUNDLED", root / "training/results"),
    )
    app.state.balance_runs = runs
    assets = Path(os.environ.get("DUCKKING_SIM_DIR", root / "external"))

    @app.get("/api/balance/runs")
    async def list_runs():
        return JSONResponse(
            {"runs": runs.list(), "training_enabled": runs.enabled, "active_run": runs.active_id},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/balance/runs/{run}")
    async def run_detail(run: str):
        try:
            return JSONResponse(runs.details(run), headers={"Cache-Control": "no-store"})
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/balance/train", status_code=202)
    async def train(body: dict):
        try:
            if set(body) - {"level", "steps", "seed"} or any(
                type(v) is not int for v in body.values()
            ):
                raise ValueError("训练参数应为关卡、步数预算与种子")
            return await runs.launch(
                body.get("level", 1), body.get("steps", 16384), body.get("seed", 42), assets
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/balance/runs/{run}/cancel", status_code=202)
    async def cancel(run: str):
        try:
            return await runs.cancel(run)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/balance/prepare")
    async def prepare(room: str = "1", replace: bool = True):
        selected = get_room(room)
        async with selected.scene_lock:
            current = selected.scene_motion
            if current and getattr(current.backend, "scene", None) == "balance":
                return await current.snapshot()
            if current and not replace:
                raise HTTPException(409, {
                    "code": "scene_conflict",
                    "message": "本房间已有其他场景。点击“切换为圆盘”会结束原场景；也可新建房间。",
                })
            if selected.voice:
                raise HTTPException(409, "请先断开当前房间语音，再切换物理世界")
            if current:
                await current.close()
                selected.scene_motion = None
            async with app.state.physics_lock:
                # A standard warm world cannot be reused for this different physics model.
                await app.state.warm_worlds.discard()
                if sum(r.scene_motion is not None for r in app.state.rooms.values()) >= (
                    app.state.room_registry.physics_limit
                ):
                    raise HTTPException(409, "物理场景已达并发上限，请释放空闲场景")
                try:
                    from .balance_backend import BalanceBackend

                    backend = await asyncio.to_thread(BalanceBackend, assets, runs)
                except Exception as exc:
                    raise HTTPException(
                        503, "平衡场景加载失败，请检查官方仿真资源与服务器日志"
                    ) from exc
                selected.scene_motion = MotionController(backend)
            return await selected.scene_motion.snapshot()

    @app.post("/api/balance/command")
    async def command(body: dict, room: str = "1"):
        selected = get_room(room)
        current = selected.scene_motion
        if current is None or getattr(current.backend, "scene", None) != "balance":
            raise HTTPException(409, "请先准备平衡教练场景")
        try:
            return await current.backend.invoke(body)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
