"""App-level singleton wiring WatcherCore + EventBus + auth token.

A single ``AppState`` is attached to ``app.state.printwatcher`` at app
construction time. Routes pull it via the ``get_state`` FastAPI dependency.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import Request

from printwatcher.core import load_preferences

if TYPE_CHECKING:  # avoid runtime import cycles for typing only
    from printwatcher.core import WatcherCore
    from printwatcher.server.dto import UpdateCheckDto
    from printwatcher.server.events import EventBus


@dataclass
class AppState:
    watcher: WatcherCore
    events: EventBus
    token: str
    app_version: str = ""
    extra: dict = field(default_factory=dict)
    # _prefs_cache stays a raw dict because preferences.json holds a flat
    # union of PreferencesDto fields and the freeform printer_defaults
    # subkey — tightening to PreferencesDto would lose the latter.
    # Validation happens at the API boundary in routes/prefs.py.
    _prefs_cache: dict | None = field(default=None, repr=False)
    _prefs_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    # GitHub release-check cache. Storing the typed DTO directly so the
    # route never re-validates against an opaque dict on cache hits.
    update_check_cache: tuple[float, UpdateCheckDto] | None = field(default=None, repr=False)
    _update_check_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get_preferences(self) -> dict:
        """Return cached preferences. Reads disk once per process unless
        ``invalidate_preferences()`` is called (e.g. after ``PUT
        /api/preferences``)."""
        with self._prefs_lock:
            if self._prefs_cache is None:
                self._prefs_cache = load_preferences()
            return dict(self._prefs_cache)

    def invalidate_preferences(self, fresh: dict | None = None) -> None:
        """Drop the cache, or replace it directly with ``fresh`` to skip the
        next disk read."""
        with self._prefs_lock:
            self._prefs_cache = dict(fresh) if fresh is not None else None


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.printwatcher
    return state
