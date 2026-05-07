"""Regression tests for confirmed correctness bugs in WatcherCore.

Reproduces and locks in fixes for three bugs found during senior-engineer
review:
  1. ``stats['today']`` was seeded once at startup and never incremented.
  2. ``PrinterWorker`` dedup compared ``Path`` objects directly, so
     ``Path('/x/y')`` and a non-normalized variant of the same physical
     file were treated as distinct submissions.
  3. ``WatcherEventForwarder`` was attached on every FastAPI lifespan
     startup with no detach, so subscriber lists grew unboundedly.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from printwatcher.core import (
    PrinterWorker,
    PrintOptions,
    PrintRecord,
    WatcherCore,
)


@pytest.fixture
def watcher(tmp_path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    return WatcherCore(
        watch_dir=inbox,
        sumatra=Path("/nonexistent/sumatra.exe"),
        history_path=tmp_path / "h.json",
    )


# --- bug #1 -----------------------------------------------------------------

def test_today_counter_increments_on_successful_print(watcher: WatcherCore) -> None:
    """A successful print today must bump stats['today'], not just printed."""
    assert watcher.stats["today"] == 0

    today_iso = datetime.now().date().isoformat()
    record = PrintRecord(
        timestamp=f"{today_iso}T10:00:00",
        filename="a.pdf",
        status="ok",
    )
    watcher._dispatch_stat("printed", 1)
    watcher._dispatch_history(record)

    assert watcher.stats["printed"] == 1
    assert watcher.stats["today"] == 1, (
        "today counter must advance when a successful print is recorded today"
    )


def test_today_counter_recomputes_on_date_rollover(watcher: WatcherCore) -> None:
    """Records dated 'yesterday' must not contribute to today's count."""
    yesterday = "1999-01-01"  # any past date
    watcher._dispatch_history(PrintRecord(
        timestamp=f"{yesterday}T10:00:00",
        filename="old.pdf",
        status="ok",
    ))
    watcher._dispatch_stat("printed", 1)
    assert watcher.stats["today"] == 0, (
        "old prints must not count toward today"
    )


# --- bug #2 -----------------------------------------------------------------

def _make_worker(tmp_path) -> PrinterWorker:
    inbox = tmp_path / "in"
    inbox.mkdir()
    printed = tmp_path / "_printed"
    printed.mkdir()
    return PrinterWorker(
        sumatra=Path("/nope"),
        watch_dir=inbox,
        printed_dir=printed,
        log_cb=lambda _line: None,
        stat_cb=lambda *_a: None,
        options_provider=lambda: PrintOptions(),
        history_cb=lambda _record: None,
    )


def test_inflight_dedup_normalizes_paths(tmp_path) -> None:
    """Duplicate submits for the same physical file via different Path forms
    must be deduplicated."""
    worker = _make_worker(tmp_path)
    target = tmp_path / "in" / "doc.pdf"
    target.write_bytes(b"%PDF-1.4 fake")

    canonical = target.resolve()
    # Same physical file, but a non-canonical Path form (a parent-traversal
    # segment that pathlib keeps verbatim and only resolve() collapses).
    # Cross-platform: works on POSIX and Windows alike.
    drift = target.parent / "sub" / ".." / target.name
    assert canonical != drift  # baseline: they compare unequal
    assert drift.resolve() == canonical  # but resolve to same file

    worker.submit(canonical)
    worker.submit(drift)

    assert len(worker.inflight_paths) == 1, (
        "two submissions of the same physical file must dedupe"
    )


# --- bug #3 -----------------------------------------------------------------

def test_lifespan_does_not_leak_subscribers(tmp_path) -> None:
    """Each FastAPI lifespan cycle must end with no extra WatcherCore
    subscribers — otherwise events fan-out N× after N restarts."""
    from fastapi.testclient import TestClient

    from printwatcher.server.app import create_app
    from printwatcher.server.events import EventBus

    inbox = tmp_path / "in"
    inbox.mkdir()
    watcher = WatcherCore(
        watch_dir=inbox,
        sumatra=Path("/nope"),
        history_path=tmp_path / "h.json",
    )
    app = create_app(watcher, EventBus(), token="x", auto_start=False)

    for _ in range(3):
        with TestClient(app):
            pass

    # All four subscriber lists must be empty after teardown.
    assert watcher._log_subs == []
    assert watcher._stat_subs == []
    assert watcher._history_subs == []
    assert watcher._pending_subs == []
