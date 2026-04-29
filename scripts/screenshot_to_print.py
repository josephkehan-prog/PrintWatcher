"""Watch a Screenshots folder and copy each new image into PrintInbox.

Default source: %USERPROFILE%\\OneDrive\\Pictures\\Screenshots (override with
--source). Images are copied (not moved) so they stay in your Screenshots
folder for later reference.

Usage:
    python scripts/screenshot_to_print.py
    python scripts/screenshot_to_print.py --source "C:\\Users\\me\\Pictures\\Screenshots"
    python scripts/screenshot_to_print.py --move      # move instead of copy

Uses stdlib only — no extra pip installs needed.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
import time
from pathlib import Path

POLL_INTERVAL_SEC = 3.0
STABLE_CHECKS = 2
STABLE_INTERVAL_SEC = 0.5
ALLOWED_EXTS = frozenset({".png", ".jpg", ".jpeg"})

log = logging.getLogger("printwatcher.screenshot")


def _read_path_constant(text: str, name: str) -> Path | None:
    match = re.search(rf'{name}\s*=\s*Path\(r"([^"]+)"\)', text)
    if not match:
        return None
    raw = match.group(1)
    if "YOUR_USERNAME" in raw:
        return None
    return Path(raw)


def discover_inbox() -> Path:
    sibling = Path(__file__).resolve().parent.parent / "print_watcher_tray.py"
    if sibling.exists():
        try:
            text = sibling.read_text(encoding="utf-8", errors="ignore")
            inbox = _read_path_constant(text, "WATCH_DIR")
            if inbox is not None:
                return inbox
        except OSError:
            pass
    onedrive = (
        os.environ.get("OneDrive")
        or os.environ.get("OneDriveCommercial")
        or os.environ.get("OneDriveConsumer")
    )
    base = Path(onedrive) if onedrive else Path.home() / "OneDrive"
    return base / "PrintInbox"


def discover_screenshots() -> Path:
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        candidate = Path(onedrive) / "Pictures" / "Screenshots"
        if candidate.exists():
            return candidate
    home = Path.home()
    candidates = [
        home / "Pictures" / "Screenshots",
        home / "OneDrive" / "Pictures" / "Screenshots",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return home / "Pictures" / "Screenshots"


def wait_until_stable(path: Path) -> bool:
    last = -1
    stable = 0
    while stable < STABLE_CHECKS:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False
        if size == last and size > 0:
            stable += 1
        else:
            stable = 0
            last = size
        time.sleep(STABLE_INTERVAL_SEC)
    return True


def transfer(source: Path, target_dir: Path, move: bool) -> Path | None:
    if not wait_until_stable(source):
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if target.exists():
        stem, suffix = target.stem, target.suffix
        target = target_dir / f"{stem}-{int(time.time())}{suffix}"
    try:
        if move:
            shutil.move(str(source), str(target))
        else:
            shutil.copy2(str(source), str(target))
    except OSError as exc:
        log.warning("transfer failed for %s: %s", source.name, exc)
        return None
    return target


def watch(source_dir: Path, inbox: Path, move: bool) -> None:
    log.info("watching %s -> %s (%s)", source_dir, inbox, "move" if move else "copy")
    seen: set[Path] = set()
    # Mark existing files as already-seen so we don't blast every old screenshot
    if source_dir.exists():
        for entry in source_dir.iterdir():
            if entry.is_file() and entry.suffix.lower() in ALLOWED_EXTS:
                seen.add(entry)
    while True:
        try:
            if not source_dir.exists():
                time.sleep(POLL_INTERVAL_SEC)
                continue
            for entry in source_dir.iterdir():
                if not entry.is_file() or entry.suffix.lower() not in ALLOWED_EXTS:
                    continue
                if entry in seen:
                    continue
                seen.add(entry)
                target = transfer(entry, inbox, move)
                if target:
                    log.info("%s: %s -> %s", "moved" if move else "copied", entry.name, target.name)
        except OSError as exc:
            log.warning("scan failed: %s", exc)
        time.sleep(POLL_INTERVAL_SEC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=None,
                        help="Screenshots folder (default: auto-detect)")
    parser.add_argument("--move", action="store_true",
                        help="move instead of copy (removes from Screenshots)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    source = args.source or discover_screenshots()
    inbox = discover_inbox()

    try:
        watch(source, inbox, args.move)
    except KeyboardInterrupt:
        log.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
