"""Auto-merge subfolder daemon — combines PDFs dropped together into one packet.

Watches `<inbox>/__merge/`. When new PDFs land, the daemon waits for a
quiet period (no new arrivals for `--quiet-seconds`), then concatenates
everything currently in the folder into a single PDF and writes it to the
inbox root. Originals move into a dated subfolder of `__merge/_consumed/`
for safekeeping.

Use case: drop several student worksheets onto OneDrive at once → one
merged packet prints, not six separate jobs.

Usage:
    python scripts/auto_merge.py
    python scripts/auto_merge.py --quiet-seconds 8 --output-prefix "Period3"

Dependencies:
    python -m pip install --user pypdf
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

DEFAULT_QUIET_SECONDS = 8.0
POLL_INTERVAL_SEC = 2.0
STABLE_CHECKS = 2
STABLE_INTERVAL_SEC = 0.5
MERGE_SUBDIR = "__merge"
CONSUMED_SUBDIR = "_consumed"

log = logging.getLogger("printwatcher.auto_merge")


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


def _wait_until_stable(path: Path) -> bool:
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


def _candidates(merge_dir: Path) -> list[Path]:
    if not merge_dir.exists():
        return []
    consumed = merge_dir / CONSUMED_SUBDIR
    return sorted(
        p for p in merge_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"
        and consumed not in p.parents
    )


def _newest_mtime(paths: list[Path]) -> float:
    if not paths:
        return 0.0
    return max(p.stat().st_mtime for p in paths)


def merge_now(files: list[Path], output: Path) -> int:
    """Concatenate `files` (alphabetical) into `output`. Returns page count."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    pages_written = 0
    for path in files:
        try:
            reader = PdfReader(str(path))
        except Exception as exc:  # pragma: no cover - corrupt PDF
            log.warning("skipping %s: %s", path.name, exc)
            continue
        for page in reader.pages:
            writer.add_page(page)
            pages_written += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as fh:
        writer.write(fh)
    return pages_written


def archive_consumed(files: list[Path], consumed_dir: Path) -> None:
    consumed_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        target = consumed_dir / path.name
        if target.exists():
            stem, suffix = target.stem, target.suffix
            target = consumed_dir / f"{stem}-{int(time.time())}{suffix}"
        try:
            shutil.move(str(path), str(target))
        except OSError as exc:
            log.warning("could not archive %s: %s", path.name, exc)


def watch(inbox: Path, quiet_seconds: float, output_prefix: str) -> None:
    merge_dir = inbox / MERGE_SUBDIR
    consumed_dir = merge_dir / CONSUMED_SUBDIR
    merge_dir.mkdir(parents=True, exist_ok=True)
    log.info("watching %s; quiet=%ss", merge_dir, quiet_seconds)

    while True:
        candidates = _candidates(merge_dir)
        if not candidates:
            time.sleep(POLL_INTERVAL_SEC)
            continue
        newest = _newest_mtime(candidates)
        if (time.time() - newest) < quiet_seconds:
            time.sleep(POLL_INTERVAL_SEC)
            continue
        # Quiet period reached. Confirm every candidate is stable.
        stable = [p for p in candidates if _wait_until_stable(p)]
        if not stable:
            time.sleep(POLL_INTERVAL_SEC)
            continue

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_name = f"{output_prefix}-{timestamp}-merged.pdf"
        output = inbox / output_name
        log.info("merging %d file(s) -> %s", len(stable), output.name)
        try:
            pages = merge_now(stable, output)
        except Exception as exc:  # pragma: no cover - merge failure
            log.error("merge failed: %s", exc)
            time.sleep(POLL_INTERVAL_SEC)
            continue
        log.info("wrote %s (%d pages)", output.name, pages)
        archive_consumed(stable, consumed_dir / timestamp)
        time.sleep(POLL_INTERVAL_SEC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quiet-seconds", type=float, default=DEFAULT_QUIET_SECONDS,
                        help=f"seconds of inactivity before merging (default {DEFAULT_QUIET_SECONDS})")
    parser.add_argument("--output-prefix", default="batch",
                        help="filename prefix for the merged output (default: batch)")
    parser.add_argument("--inbox", type=Path, default=None,
                        help="override PrintInbox path")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    inbox = args.inbox or discover_inbox()

    try:
        watch(inbox, args.quiet_seconds, args.output_prefix)
    except KeyboardInterrupt:
        log.info("daemon stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
