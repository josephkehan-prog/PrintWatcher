"""Pausing the worker short-circuits ``_print_one``."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_pause_skips_print(watcher, tmp_inbox: Path):
    """When paused, the worker logs and returns without invoking subprocess."""
    watcher.pause()
    assert watcher.is_paused

    log_lines: list[str] = []
    watcher.subscribe_log(lambda line: log_lines.append(line))

    fake_pdf = tmp_inbox / "doc.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")
    # Drive the worker private path directly so we don't need a live thread.
    watcher.worker._print_one(fake_pdf)

    assert any("paused" in line and "doc.pdf" in line for line in log_lines)
    # File still in place — worker should not have moved it.
    assert fake_pdf.exists()


def test_resume_clears_pause(watcher):
    watcher.pause()
    watcher.resume()
    assert watcher.is_paused is False
