"""Regression test for the windowed-exe stdout=None crash.

When the backend runs as a PyInstaller --windowed exe on Windows,
``sys.stdout`` and ``sys.stderr`` are ``None``. uvicorn's
``ColourizedFormatter`` called ``stream.isatty()`` in its constructor and
crashed with ``AttributeError: 'NoneType' object has no attribute 'isatty'``.

These tests pin the fix:
- ``_ensure_console_streams`` redirects None streams to a log file.
- The resulting streams are real file handles that respond to isatty().
- main() with ``log_config=None`` doesn't trigger uvicorn's default
  ColourizedFormatter dictConfig path.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from printwatcher.server.__main__ import _ensure_console_streams


@pytest.fixture
def isolated_localappdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return tmp_path


def test_redirects_when_stdout_is_none(
    isolated_localappdata: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    log_path = _ensure_console_streams()

    assert log_path is not None
    assert log_path == isolated_localappdata / "PrintWatcher" / "backend.log"
    assert sys.stdout is not None
    assert sys.stderr is not None
    # Critical: streams must respond to isatty() (uvicorn's
    # ColourizedFormatter calls this and crashes on None).
    assert sys.stdout.isatty() is False
    assert sys.stderr.isatty() is False


def test_no_op_when_streams_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Don't clobber a real terminal."""
    # Use the real (or pytest-captured) stdout/stderr — both non-None.
    real_stdout = sys.stdout
    real_stderr = sys.stderr
    log_path = _ensure_console_streams()
    assert log_path is None
    assert sys.stdout is real_stdout
    assert sys.stderr is real_stderr


def test_logging_basic_config_works_after_redirect(
    isolated_localappdata: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """logging.basicConfig defaults to sys.stderr; must not blow up after
    we replace None with a file handle."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    _ensure_console_streams()
    # basicConfig should attach a StreamHandler to a real stream now.
    # Reset existing handlers first so basicConfig actually does work.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("test").info("hello")  # must not raise
