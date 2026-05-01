"""App-level singleton wiring WatcherCore + EventBus + auth token.

A single ``AppState`` is attached to ``app.state.printwatcher`` at app
construction time. Routes pull it via the ``get_state`` FastAPI dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:  # avoid runtime import cycles for typing only
    from printwatcher.core import WatcherCore
    from printwatcher.server.events import EventBus


@dataclass
class AppState:
    watcher: "WatcherCore"
    events: "EventBus"
    token: str
    app_version: str = ""
    extra: dict = field(default_factory=dict)


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.printwatcher
    return state
