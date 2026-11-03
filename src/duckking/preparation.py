"""One optional unused world; shares admission with user worlds and never runs motion."""

import asyncio
import logging
from contextlib import suppress


class WarmWorldPool:
    def __init__(self, lock, factory, eligible, *, enabled=False):
        self.lock, self.factory, self.eligible = lock, factory, eligible
        self.enabled = enabled
        self.ready = None
        self.state = 'idle' if enabled else 'disabled'

    async def prepare(self):
        if not self.enabled or self.ready is not None or self.state == 'failed':
            return
        async with self.lock:
            if self.ready is not None or not self.eligible():
                return
            self.state = 'preparing'
            building = asyncio.create_task(asyncio.to_thread(self.factory))
            try:
                self.ready = await asyncio.shield(building)
            except asyncio.CancelledError:
                # Do not abandon a native compilation after dropping its admission lock.
                with suppress(Exception):
                    abandoned = await asyncio.shield(building)
                    await abandoned.close()
                self.state = 'stopped'
                raise
            except Exception as exc:
                self.state = 'failed'
                logging.getLogger(__name__).warning(
                    'physics_prewarm_failed: %s', type(exc).__name__
                )
            else:
                self.state = 'ready'

    def take(self):
        """Called under the same admission lock; ownership transfers to one room only."""
        world, self.ready = self.ready, None
        if world is not None:
            self.state = 'idle'
        return world

    async def discard(self):
        world = self.take()
        if world is not None:
            await world.close()

    async def watch(self):
        if not self.enabled:
            return
        while True:
            await self.prepare()
            await asyncio.sleep(15)
