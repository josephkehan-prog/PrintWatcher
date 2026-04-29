"""Stamp name/date/period on PDFs dropped into PrintInbox/stamped/, then forward to PrintInbox/.

Run as a daemon next to the main watcher:

    python scripts/name_stamper.py --name "Mr. Han" --period "P3"

Or set env vars and omit flags:
    STAMP_NAME=Mr.Han STAMP_PERIOD=P3 python scripts/name_stamper.py

Workflow:
1. Drop a PDF into <inbox>/stamped/
2. This script overlays the stamp at top-right of every page
3. The stamped PDF moves to <inbox>/ where the main watcher picks it up
4. The original is removed from stamped/

Dependencies (install once):
    python -m pip install --user pypdf reportlab

Inbox path is auto-detected the same way print_watcher_ui.py does it
(reads print_watcher_tray.py if it has been bootstrap-patched, else
falls back to %OneDrive%/PrintInbox).
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

POLL_INTERVAL_SEC = 5.0
STABLE_CHECKS = 3
STABLE_INTERVAL_SEC = 1.0
STAMPED_SUBDIR = "stamped"

log = logging.getLogger("printwatcher.stamper")


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
    env_inbox = os.environ.get("STAMP_INBOX") or os.environ.get("PRINTWATCHER_INBOX")
    if env_inbox:
        return Path(env_inbox)
    onedrive = (
        os.environ.get("OneDrive")
        or os.environ.get("OneDriveCommercial")
        or os.environ.get("OneDriveConsumer")
    )
    base = Path(onedrive) if onedrive else Path.home() / "OneDrive"
    return base / "PrintInbox"


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


def build_overlay_page(stamp_text: str, page_width: float, page_height: float) -> bytes:
    """Return PDF bytes for a single overlay page sized to match the target."""
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    c.setFont("Helvetica-Bold", 10)
    c.setFillColorRGB(0.15, 0.15, 0.15)
    margin = 18
    c.drawRightString(page_width - margin, page_height - margin - 4, stamp_text)
    c.showPage()
    c.save()
    return buffer.getvalue()


def stamp_pdf(input_path: Path, output_path: Path, stamp_text: str) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(input_path))
    writer = PdfWriter()
    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        overlay_bytes = build_overlay_page(stamp_text, width, height)
        overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
        page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        writer.write(fh)


def render_stamp(name: str, period: str | None) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    parts = [name, today]
    if period:
        parts.append(period)
    return " · ".join(parts)


def process_one(path: Path, target_dir: Path, stamp_text: str) -> None:
    if not wait_until_stable(path):
        log.warning("file vanished or never stabilised: %s", path.name)
        return
    output = target_dir / path.name
    if output.exists():
        stem, suffix = output.stem, output.suffix
        output = target_dir / f"{stem}-stamped-{int(time.time())}{suffix}"
    try:
        stamp_pdf(path, output, stamp_text)
    except Exception as exc:  # pragma: no cover - dependency-import or PDF parse failure
        log.error("stamp failed for %s: %s", path.name, exc)
        return
    try:
        path.unlink()
    except OSError as exc:
        log.warning("could not remove source %s: %s", path.name, exc)
    log.info("stamped: %s -> %s", path.name, output.name)


def watch(stamped_dir: Path, target_dir: Path, stamp_text: str) -> None:
    stamped_dir.mkdir(parents=True, exist_ok=True)
    log.info("watching %s; stamp text: %s", stamped_dir, stamp_text)
    seen: set[Path] = set()
    while True:
        try:
            for entry in stamped_dir.iterdir():
                if not entry.is_file():
                    continue
                if entry.suffix.lower() != ".pdf":
                    continue
                if entry in seen:
                    continue
                seen.add(entry)
                try:
                    process_one(entry, target_dir, stamp_text)
                finally:
                    seen.discard(entry)
        except FileNotFoundError:
            pass
        time.sleep(POLL_INTERVAL_SEC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default=os.environ.get("STAMP_NAME"),
                        help="name to overlay (or set STAMP_NAME)")
    parser.add_argument("--period", default=os.environ.get("STAMP_PERIOD"),
                        help="optional period/class (or set STAMP_PERIOD)")
    parser.add_argument("--inbox", default=None,
                        help="override PrintInbox path (defaults to auto-discovery)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.name:
        parser.error("--name is required (or set STAMP_NAME env var)")

    inbox = Path(args.inbox) if args.inbox else discover_inbox()
    stamped = inbox / STAMPED_SUBDIR
    stamp_text = render_stamp(args.name, args.period)

    try:
        watch(stamped, inbox, stamp_text)
    except KeyboardInterrupt:
        log.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
