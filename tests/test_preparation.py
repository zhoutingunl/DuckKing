import asyncio
import threading

import pytest

from duckking.preparation import WarmWorldPool


class World:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


async def test_single_unused_world_transfers_once_and_refills_only_when_idle():
    created, occupied = [], False

    def factory():
        world = World()
        created.append(world)
        return world

    pool = WarmWorldPool(asyncio.Lock(), factory, lambda: not occupied, enabled=True)
    await asyncio.gather(pool.prepare(), pool.prepare())
    assert len(created) == 1 and pool.state == 'ready'
    async with pool.lock:
        owned = pool.take()
        occupied = True
        assert pool.take() is None
    await pool.prepare()
    assert len(created) == 1 and not owned.closed
    await owned.close()
    occupied = False
    await pool.prepare()
    assert len(created) == 2
    await pool.discard()
    assert created[-1].closed and pool.ready is None


async def test_disabled_or_failed_prewarm_never_silently_retries_or_creates_a_preview():
    calls = []

    def fail():
        calls.append(True)
        raise ValueError('missing assets')

    pool = WarmWorldPool(asyncio.Lock(), fail, lambda: True)
    await pool.watch()
    await pool.prepare()
    assert calls == [] and pool.state == 'disabled'
    pool.enabled = True
    await pool.prepare()
    await pool.prepare()
    assert calls == [True] and pool.state == 'failed' and pool.take() is None


async def test_shutdown_waits_for_native_build_and_closes_the_unclaimed_world():
    started, release = threading.Event(), threading.Event()
    world = World()

    def factory():
        started.set()
        assert release.wait(5)
        return world

    pool = WarmWorldPool(asyncio.Lock(), factory, lambda: True, enabled=True)
    task = asyncio.create_task(pool.prepare())
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(.01)
        assert pool.lock.locked() and not world.closed
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert world.closed and pool.ready is None and not pool.lock.locked()


async def test_watch_keeps_one_ready_world_and_cancels_cleanly():
    prepared = asyncio.Event()

    class ObservablePool(WarmWorldPool):
        async def prepare(self):
            await super().prepare()
            prepared.set()

    pool = ObservablePool(asyncio.Lock(), World, lambda: True, enabled=True)
    task = asyncio.create_task(pool.watch())
    await asyncio.wait_for(prepared.wait(), 2)
    world = pool.ready
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await pool.discard()
    assert world.closed


async def test_real_prewarmed_world_is_claimed_once_without_starting_a_background_motion(tmp_path):
    from duckking.app import create_app
    from duckking.config import Settings
    from duckking.motion import Action

    app = create_app(settings=Settings(data_dir=tmp_path, prewarm_physics=True))
    pool = app.state.warm_worlds
    await pool.prepare()
    warm = pool.ready
    assert warm.kind == "mujoco" and warm.task is None
    start = next(r.endpoint for r in app.routes if r.path == "/api/scenes/start")
    record = await start(Action(name="scene_ball"), room="1")
    controller = app.state.scene_motion
    assert controller.backend is warm and pool.ready is None
    await pool.prepare()
    assert pool.ready is None  # No spare allocation while a user owns a physical world.
    assert (await controller.wait(record["id"]))["status"] == "completed"
    close = next(r.endpoint for r in app.routes if r.path == "/api/scenes/close")
    await close(room="1", if_unused=False)
    await pool.prepare()
    assert pool.ready is not None and pool.ready is not warm
    await pool.discard()
