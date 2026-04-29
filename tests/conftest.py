"""Shared pytest fixtures + tkinter/pystray shims for headless CI.

The watcher module imports tkinter and watchdog at module load. CI runs on
headless Linux without a Tk display, so we stub those modules before the
target module is imported.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _install_stubs() -> None:
    """Install minimal fakes for the heavy GUI / watchdog imports."""
    if "watchdog" not in sys.modules:
        for name in ("watchdog", "watchdog.events", "watchdog.observers"):
            sys.modules[name] = types.ModuleType(name)
        sys.modules["watchdog.events"].FileSystemEvent = object
        sys.modules["watchdog.events"].FileSystemEventHandler = object
        sys.modules["watchdog.observers"].Observer = object

    try:
        import tkinter  # noqa: F401
    except Exception:
        for name in ("tkinter", "tkinter.ttk"):
            sys.modules[name] = types.ModuleType(name)
        sys.modules["tkinter"].Tk = object
        sys.modules["tkinter"].TclError = Exception


_install_stubs()
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def watcher_module():
    """Import print_watcher_ui with stubs in place. Reimports per test."""
    if "print_watcher_ui" in sys.modules:
        del sys.modules["print_watcher_ui"]
    import print_watcher_ui  # noqa: WPS433
    return print_watcher_ui


@pytest.fixture
def tmp_inbox(tmp_path):
    """A temporary 'PrintInbox' directory with a _printed/ subfolder."""
    inbox = tmp_path / "PrintInbox"
    inbox.mkdir()
    (inbox / "_printed").mkdir()
    return inbox
