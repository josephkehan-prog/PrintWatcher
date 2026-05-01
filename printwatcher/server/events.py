"""Thread-safe pub/sub bus for watcher events.

The watcher runs on background threads; uvicorn runs on an asyncio loop. The
bus accepts publishes from either side and fan-outs to every subscriber's
``asyncio.Queue``. Subscribers are typically WebSocket connections that
forward each frame to the WinUI shell.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger("printwatcher.server.events")


class EventBus:
    """In-process publish/subscribe over ``asyncio.Queue`` instances.

    A subscriber receives every frame published *after* it subscribed. There
    is no replay buffer — clients always start with a snapshot from
    ``GET /api/state`` and then consume the live stream.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._loop = loop
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._max_queue = 256

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Attach to the running event loop. Must be called before publish."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def publish(self, event: dict[str, Any]) -> None:
        """Best-effort enqueue from any thread.

        Drops frames for slow subscribers rather than blocking the publisher.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        for queue in tuple(self._subscribers):
            try:
                loop.call_soon_threadsafe(self._enqueue, queue, event)
            except RuntimeError:
                # Loop already shutting down — drop.
                continue

    @staticmethod
    def _enqueue(queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            log.warning("event subscriber queue full; dropping %s", event.get("type"))

    def subscriber_count(self) -> int:
        return len(self._subscribers)
