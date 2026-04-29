"""Strip a configurable header/footer band off PDFs before printing.

One-shot:
    python scripts/redact.py input.pdf --header 60 --footer 40 -o output.pdf

Watch mode (drop into <inbox>/redact/, processed PDFs land in inbox root):
    python scripts/redact.py --watch

Bands are measured in PDF points from the corresponding edge (1 inch = 72 pt).
The header band is removed from the top, the footer band from the bottom.
Crop only — original content is preserved, just clipped via mediabox/cropbox.

Dependencies (install once):
    python -m pip install --user pypdf
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path

POLL_INTERVAL_SEC = 5.0
STABLE_CHECKS = 3
STABLE_INTERVAL_SEC = 1.0
REDACT_SUBDIR = "redact"

log = logging.getLogger("printwatcher.redact")


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


def crop_pdf(input_path: Path, output_path: Path, header: float, footer: float) -> None:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import RectangleObject

    reader = PdfReader(str(input_path))
    writer = PdfWriter()
    for page in reader.pages:
        box = page.mediabox
        lower_left_x = float(box.lower_left[0])
        lower_left_y = float(box.lower_left[1]) + footer
        upper_right_x = float(box.upper_right[0])
        upper_right_y = float(box.upper_right[1]) - header
        if upper_right_y <= lower_left_y:
            log.warning("page collapses to zero height with these bands; copying as-is")
            writer.add_page(page)
            continue
        cropped = RectangleObject((lower_left_x, lower_left_y, upper_right_x, upper_right_y))
        page.mediabox = cropped
        page.cropbox = cropped
        writer.add_page(page)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        writer.write(fh)


def process_one(source: Path, target_dir: Path, header: float, footer: float) -> None:
    if not wait_until_stable(source):
        log.warning("file vanished or never stabilised: %s", source.name)
        return
    output = target_dir / source.name
    if output.exists():
        stem, suffix = output.stem, output.suffix
        output = target_dir / f"{stem}-redacted-{int(time.time())}{suffix}"
    try:
        crop_pdf(source, output, header, footer)
    except Exception as exc:  # pragma: no cover - PDF parse failure
        log.error("redact failed for %s: %s", source.name, exc)
        return
    try:
        source.unlink()
    except OSError as exc:
        log.warning("could not remove source %s: %s", source.name, exc)
    log.info("redacted: %s -> %s", source.name, output.name)


def watch(redact_dir: Path, target_dir: Path, header: float, footer: float) -> None:
    redact_dir.mkdir(parents=True, exist_ok=True)
    log.info("watching %s; header=%spt footer=%spt", redact_dir, header, footer)
    seen: set[Path] = set()
    while True:
        try:
            for entry in redact_dir.iterdir():
                if not entry.is_file() or entry.suffix.lower() != ".pdf":
                    continue
                if entry in seen:
                    continue
                seen.add(entry)
                try:
                    process_one(entry, target_dir, header, footer)
                finally:
                    seen.discard(entry)
        except FileNotFoundError:
            pass
        time.sleep(POLL_INTERVAL_SEC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", nargs="?", type=Path, help="PDF to redact (omit when --watch)")
    parser.add_argument("-o", "--output", type=Path, help="output PDF path")
    parser.add_argument("--header", type=float, default=0.0,
                        help="points to crop from the top (default: 0)")
    parser.add_argument("--footer", type=float, default=0.0,
                        help="points to crop from the bottom (default: 0)")
    parser.add_argument("--watch", action="store_true",
                        help="watch <inbox>/redact/ and write results to inbox root")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.watch:
        if args.input is not None or args.output is not None:
            parser.error("--watch is exclusive with positional input / -o output")
        inbox = discover_inbox()
        try:
            watch(inbox / REDACT_SUBDIR, inbox, args.header, args.footer)
        except KeyboardInterrupt:
            log.info("stopped")
        return 0

    if args.input is None:
        parser.error("input PDF is required (or use --watch)")
    if not args.input.exists():
        parser.error(f"input not found: {args.input}")
    output = args.output or args.input.with_name(f"{args.input.stem}-redacted{args.input.suffix}")
    crop_pdf(args.input, output, args.header, args.footer)
    log.info("wrote %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
