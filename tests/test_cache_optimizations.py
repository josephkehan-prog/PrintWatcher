"""Cache behavior tests for the two latency optimizations.

* ``list_printers()`` has a 30 s TTL cache; a second call inside the
  window must not re-shell out.
* ``AppState.get_preferences()`` reads disk once; ``PUT /api/preferences``
  must invalidate so the new value is visible without restarting.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from printwatcher import core

# --- printers TTL cache -----------------------------------------------------

@pytest.fixture(autouse=True)
def _drop_printer_cache():
    core._invalidate_printers_cache()
    yield
    core._invalidate_printers_cache()


def test_list_printers_caches_within_ttl() -> None:
    """Two calls inside the TTL window must hit the underlying enumerator
    exactly once."""
    with patch.object(core, "_list_printers_uncached", return_value=["P1", "P2"]) as mock:
        first = core.list_printers()
        second = core.list_printers()

    assert first == ["P1", "P2"]
    assert second == ["P1", "P2"]
    assert mock.call_count == 1, "second call within TTL must come from cache"


def test_list_printers_returns_copies_not_aliases() -> None:
    """Mutating a returned list must not poison the cache."""
    with patch.object(core, "_list_printers_uncached", return_value=["P1"]):
        first = core.list_printers()
        first.append("MUTATED")
        second = core.list_printers()

    assert second == ["P1"], "cached list must be isolated from caller mutations"


def test_invalidate_drops_cache() -> None:
    with patch.object(core, "_list_printers_uncached", return_value=["P1"]) as mock:
        core.list_printers()
        core._invalidate_printers_cache()
        core.list_printers()
    assert mock.call_count == 2


# --- preferences cache ------------------------------------------------------

def test_appstate_caches_preferences(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """First call reads from disk, second call must NOT re-read."""
    from printwatcher.server.state import AppState

    prefs_file = tmp_path / "preferences.json"
    prefs_file.write_text(json.dumps({"theme": "Ocean", "hold_mode": False}))
    monkeypatch.setattr("printwatcher.core._preferences_path", lambda: prefs_file)

    state = AppState(watcher=object(), events=object(), token="x")  # type: ignore[arg-type]

    with patch("printwatcher.server.state.load_preferences", wraps=core.load_preferences) as spy:
        a = state.get_preferences()
        b = state.get_preferences()

    assert a == b == {"theme": "Ocean", "hold_mode": False}
    assert spy.call_count == 1, "second call must come from the cache"


def test_appstate_invalidates_on_put(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """invalidate_preferences(fresh=...) must replace the cache without a
    disk read."""
    from printwatcher.server.state import AppState

    prefs_file = tmp_path / "preferences.json"
    prefs_file.write_text(json.dumps({"theme": "Ocean"}))
    monkeypatch.setattr("printwatcher.core._preferences_path", lambda: prefs_file)

    state = AppState(watcher=object(), events=object(), token="x")  # type: ignore[arg-type]
    state.get_preferences()  # warm

    state.invalidate_preferences(fresh={"theme": "Forest"})

    with patch("printwatcher.server.state.load_preferences") as never_called:
        out = state.get_preferences()
    never_called.assert_not_called()
    assert out == {"theme": "Forest"}
