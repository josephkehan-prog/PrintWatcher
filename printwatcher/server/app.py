"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI

from printwatcher.core import APP_VERSION, PrintRecord, WatcherCore
from printwatcher.server.events import EventBus
from printwatcher.server.routes import ALL_ROUTERS
from printwatcher.server.state import AppState
from printwatcher.server.websocket import router as ws_router

log = logging.getLogger("printwatcher.server.app")


class WatcherEventForwarder:
    """Forward every WatcherCore event onto the EventBus as JSON frames.

    Extracted as a class (not closures) so each handler is testable in
    isolation and the wiring step has no hidden state. ``attach`` collects
    the unsubscribe callables WatcherCore returns; ``detach`` calls them so
    repeated lifespan cycles don't accumulate duplicate subscribers.
    """

    def __init__(self, events: EventBus) -> None:
        self._events = events
        self._unsubscribers: list = []

    def attach(self, watcher: WatcherCore) -> None:
        self._unsubscribers = [
            watcher.subscribe_log(self.on_log),
            watcher.subscribe_stat(self.on_stat),
            watcher.subscribe_history(self.on_history),
            watcher.subscribe_pending(self.on_pending),
        ]

    def detach(self) -> None:
        for unsub in self._unsubscribers:
            try:
                unsub()
            except Exception:  # pragma: no cover - best-effort teardown
                log.exception("forwarder detach failed")
        self._unsubscribers = []

    def on_log(self, line: str) -> None:
        self._events.publish({
            "type": "log",
            "ts": datetime.now().isoformat(timespec="seconds"),
            "level": "info",
            "line": line,
        })

    def on_stat(self, key: str, delta: int, value: int) -> None:
        self._events.publish({"type": "stat", "key": key, "delta": delta, "value": value})

    def on_history(self, record: PrintRecord) -> None:
        self._events.publish({"type": "history", "record": record.__dict__})

    def on_pending(self, items) -> None:
        self._events.publish({
            "type": "pending",
            "items": [{"path": str(p), "name": p.name} for p in items],
        })


def create_app(
    watcher: WatcherCore,
    events: EventBus,
    token: str,
    *,
    app_version: str = APP_VERSION,
    auto_start: bool = True,
) -> FastAPI:
    """Build a FastAPI app bound to ``watcher`` + ``events``.

    ``auto_start=True`` starts the WatcherCore (Observer + Worker + poller)
    on app startup. Tests pass ``False`` to skip filesystem side effects.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        events.bind_loop(asyncio.get_running_loop())
        forwarder = WatcherEventForwarder(events)
        forwarder.attach(watcher)
        if auto_start:
            watcher.start()
        try:
            yield
        finally:
            forwarder.detach()
            if auto_start:
                watcher.stop()

    app = FastAPI(title="PrintWatcher backend", version=app_version, lifespan=lifespan)
    app.state.printwatcher = AppState(
        watcher=watcher,
        events=events,
        token=token,
        app_version=app_version,
    )

    for router in ALL_ROUTERS:
        app.include_router(router)
    app.include_router(ws_router)

    return app
