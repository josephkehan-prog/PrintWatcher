"""Fixtures for FastAPI surface tests.

Builds an in-memory ``WatcherCore`` against a tmp inbox and wires it into a
FastAPI app via ``create_app(..., auto_start=False)`` so no Observer threads
or filesystem polling kick in during the suite.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _install_stubs() -> None:
    if "watchdog" not in sys.modules:
        for name in ("watchdog", "watchdog.events", "watchdog.observers"):
            sys.modules[name] = types.ModuleType(name)

        class _StubEvent:
            is_directory = False
            src_path = ""
            dest_path = ""

        class _StubHandler:
            def __init__(self, *a, **kw): ...
            def on_created(self, *a, **kw): ...
            def on_moved(self, *a, **kw): ...

        class _StubObserver:
            def __init__(self) -> None:
                self._stopped = False

            def schedule(self, *a, **kw) -> None: ...
            def start(self) -> None: ...
            def stop(self) -> None:
                self._stopped = True

            def join(self, *a, **kw) -> None: ...

        sys.modules["watchdog.events"].FileSystemEvent = _StubEvent
        sys.modules["watchdog.events"].FileSystemEventHandler = _StubHandler
        sys.modules["watchdog.observers"].Observer = _StubObserver


_install_stubs()
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def tmp_inbox(tmp_path: Path) -> Path:
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    return inbox


@pytest.fixture
def tmp_history(tmp_path: Path) -> Path:
    return tmp_path / "history.json"


@pytest.fixture
def watcher(tmp_inbox: Path, tmp_history: Path):
    from printwatcher.core import WatcherCore

    core = WatcherCore(
        watch_dir=tmp_inbox,
        sumatra=Path("/nonexistent/sumatra.exe"),
        history_path=tmp_history,
    )
    yield core
    core.stop()


@pytest.fixture
async def event_bus():
    """Bind the bus to whatever event loop pytest-asyncio gave the test."""
    from printwatcher.server.events import EventBus
    bus = EventBus()
    bus.bind_loop(asyncio.get_running_loop())
    return bus


@pytest.fixture
def token() -> str:
    return "deadbeef" * 8


@pytest.fixture
def app(watcher, event_bus, token):
    from printwatcher.server.app import create_app
    return create_app(watcher, event_bus, token, auto_start=False)


@pytest.fixture
async def client(app):
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
