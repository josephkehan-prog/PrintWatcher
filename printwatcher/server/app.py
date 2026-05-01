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


def _wire_subscriptions(watcher: WatcherCore, events: EventBus) -> None:
    """Forward every WatcherCore event onto the bus as JSON frames."""

    def on_log(line: str) -> None:
        events.publish({
            "type": "log",
            "ts": datetime.now().isoformat(timespec="seconds"),
            "level": "info",
            "line": line,
        })

    def on_stat(key: str, delta: int, value: int) -> None:
        events.publish({"type": "stat", "key": key, "delta": delta, "value": value})

    def on_history(record: PrintRecord) -> None:
        events.publish({"type": "history", "record": record.__dict__})

    def on_pending(items) -> None:
        events.publish({
            "type": "pending",
            "items": [{"path": str(p), "name": p.name} for p in items],
        })

    watcher.subscribe_log(on_log)
    watcher.subscribe_stat(on_stat)
    watcher.subscribe_history(on_history)
    watcher.subscribe_pending(on_pending)


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
        _wire_subscriptions(watcher, events)
        if auto_start:
            watcher.start()
        try:
            yield
        finally:
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
