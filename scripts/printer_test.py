"""One-page printer calibration sheet — drop on any printer to confirm health.

Generates a Letter-size PDF with:

- 1" ruler ticks along all four edges (and 0.25" inside major ticks)
- Centred crosshair with mm + inch markers — quick alignment check
- 11-step gray ramp 0% -> 100%
- CMY + RGB + Black colour bars
- Font samples at 6 / 8 / 10 / 12 / 14 / 18 / 24 / 36 pt
- Serial and date in the corners so you can spot which test page was
  the latest

Usage:
    python scripts/printer_test.py
    python scripts/printer_test.py --to-inbox       # auto-print via watcher
    python scripts/printer_test.py --out test.pdf
    python scripts/printer_test.py --serial "ABC-123"

Dependencies:
    python -m pip install --user reportlab
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

log = logging.getLogger("printwatcher.printer_test")


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


def render(output: Path, serial: str) -> None:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError(
            "reportlab not installed — `python -m pip install --user reportlab`"
        ) from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    page_w, page_h = letter
    c = canvas.Canvas(str(output), pagesize=letter)

    # Outer crop marks (corner ticks)
    c.setLineWidth(0.5)
    c.setStrokeGray(0.0)
    tick = 18
    for x, y in ((0, 0), (page_w, 0), (0, page_h), (page_w, page_h)):
        c.line(x, y, x + (tick if x == 0 else -tick), y)
        c.line(x, y, x, y + (tick if y == 0 else -tick))

    margin = 54
    inch = 72

    # Top title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, page_h - margin, "PrintWatcher · Calibration page")
    c.setFont("Helvetica", 9)
    c.setFillGray(0.45)
    c.drawString(margin, page_h - margin - 14,
                 f"serial {serial}  ·  generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.setFillGray(0)

    # 1-inch ruler ticks along edges
    c.setLineWidth(0.4)
    for i in range(int(page_w / inch) + 1):
        x = i * inch
        c.line(x, 0, x, 14)
        c.line(x, page_h, x, page_h - 14)
        c.setFont("Helvetica", 7)
        c.drawString(x + 2, 4, f"{i}")
    for i in range(int(page_h / inch) + 1):
        y = i * inch
        c.line(0, y, 14, y)
        c.line(page_w, y, page_w - 14, y)
        c.drawString(4, y + 2, f"{i}")
    # Quarter-inch ticks
    for x in range(0, int(page_w), inch // 4):
        if x % inch == 0:
            continue
        c.line(x, 0, x, 6)
        c.line(x, page_h, x, page_h - 6)

    # Centre crosshair
    cx, cy = page_w / 2, page_h / 2
    c.setStrokeGray(0.3)
    c.setLineWidth(0.6)
    c.line(cx - 36, cy, cx + 36, cy)
    c.line(cx, cy - 36, cx, cy + 36)
    c.circle(cx, cy, 24, stroke=1, fill=0)
    c.setStrokeGray(0)

    # Gray ramp
    ramp_y = page_h - margin - 64
    swatch_w = (page_w - margin * 2) / 11
    c.setFont("Helvetica", 8)
    for i in range(11):
        gray = 1.0 - (i / 10)
        c.setFillGray(gray)
        c.rect(margin + i * swatch_w, ramp_y - 36, swatch_w - 2, 36, fill=1, stroke=0)
        c.setFillGray(0)
        c.drawString(margin + i * swatch_w + 4, ramp_y - 50, f"{i*10}%")

    # Colour bars (CMY + RGB + K)
    color_y = ramp_y - 90
    color_h = 36
    palette = (
        ("Cyan", (0, 1, 1, 0)),
        ("Magenta", (1, 0, 1, 0)),
        ("Yellow", (1, 1, 0, 0)),
        ("Red", (1, 0, 0, 0)),
        ("Green", (0, 1, 0, 0)),
        ("Blue", (0, 0, 1, 0)),
        ("Black", (0, 0, 0, 1)),
    )
    bar_w = (page_w - margin * 2) / len(palette)
    for i, (label, rgba) in enumerate(palette):
        # rgba is (R complement, G complement, B complement, K) for the
        # CMYK bars; reportlab takes RGB so convert.
        r, g, b, k = rgba
        rgb = (1 - r) * (1 - k), (1 - g) * (1 - k), (1 - b) * (1 - k)
        c.setFillColorRGB(*rgb)
        c.rect(margin + i * bar_w, color_y - color_h, bar_w - 2, color_h, fill=1, stroke=0)
        c.setFillGray(0)
        c.setFont("Helvetica", 8)
        c.drawString(margin + i * bar_w + 4, color_y - color_h - 12, label)

    # Font sample ladder
    sample_y = color_y - color_h - 48
    sizes = (36, 24, 18, 14, 12, 10, 8, 6)
    for size in sizes:
        c.setFont("Helvetica", size)
        c.drawString(margin, sample_y, f"{size:>2}pt  The quick brown fox jumps over the lazy dog")
        sample_y -= size + 2

    # Edge-margin proof: thin border at exact 0.25" from each edge
    c.setLineWidth(0.4)
    c.setStrokeGray(0.6)
    edge = inch * 0.25
    c.rect(edge, edge, page_w - 2 * edge, page_h - 2 * edge, stroke=1, fill=0)
    c.setFont("Helvetica", 7)
    c.setFillGray(0.55)
    c.drawString(edge + 4, edge + 4, "0.25\" margin")
    c.setFillGray(0)

    c.showPage()
    c.save()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None,
                        help="output PDF path (default: ./printer-test.pdf)")
    parser.add_argument("--to-inbox", action="store_true",
                        help="drop into PrintWatcher inbox so it auto-prints")
    parser.add_argument("--serial", default=None,
                        help="custom serial label (default: short uuid)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    serial = args.serial or uuid.uuid4().hex[:8].upper()

    if args.to_inbox:
        output = discover_inbox() / f"printer-test-{serial}.pdf"
    else:
        output = args.out or Path.cwd() / f"printer-test-{serial}.pdf"

    try:
        render(output, serial)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 2
    log.info("wrote %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
