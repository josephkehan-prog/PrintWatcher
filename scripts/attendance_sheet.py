"""Generate today's blank attendance sheet for a class roster.

Renders a Letter-size PDF with one row per scholar plus columns for
Present / Tardy / Absent and a Notes field. Optional check-in time
column for staggered arrivals.

Usage:
    python scripts/attendance_sheet.py --class Hamilton
    python scripts/attendance_sheet.py --class Hamilton --to-inbox
    python scripts/attendance_sheet.py --class Hamilton --date 2026-04-30 \\
        --include-time --out today.pdf

Run daily via Task Scheduler with `--to-inbox` so a fresh sheet prints
each morning at 6:30 AM:

    schtasks /Create /TN "PrintWatcher-Attendance" /SC DAILY /ST 06:30 ^
      /TR "PrintWatcher-cli attendance Hamilton --to-inbox"

Dependencies:
    python -m pip install --user reportlab
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger("printwatcher.attendance")


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


def rosters_dir() -> Path:
    base = os.environ.get("APPDATA")
    return (
        Path(base) / "PrintWatcher" / "rosters"
        if base else Path.home() / ".printwatcher" / "rosters"
    )


_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(name: str) -> str:
    cleaned = _SLUG.sub("_", name.strip()).strip("._")
    return cleaned or "scholar"


def load_names(class_name: str, override: Path | None) -> list[str]:
    path = override or (rosters_dir() / f"{slugify(class_name)}.csv")
    if not path.exists():
        raise FileNotFoundError(path)
    names: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = (row.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def render(
    class_name: str,
    names: list[str],
    output: Path,
    target_date: date,
    include_time: bool,
) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    output.parent.mkdir(parents=True, exist_ok=True)
    page_w, page_h = letter
    c = canvas.Canvas(str(output), pagesize=letter)

    margin = 54
    y = page_h - margin

    c.setFont("Helvetica-Bold", 22)
    c.drawString(margin, y, "Attendance")
    y -= 24
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin, y, class_name)
    y -= 18
    c.setFont("Helvetica", 11)
    c.setFillGray(0.45)
    c.drawString(margin, y, target_date.strftime("%A, %B %d, %Y"))
    c.setFillGray(0)
    y -= 26

    columns = ["#", "Scholar", "P", "T", "A"]
    col_widths = [22, 220, 32, 32, 32]
    if include_time:
        columns.append("Time")
        col_widths.append(60)
    columns.append("Notes")
    col_widths.append(page_w - 2 * margin - sum(col_widths))

    # Column headers
    c.setFont("Helvetica-Bold", 9)
    x = margin
    for label, width in zip(columns, col_widths):
        c.drawString(x + 4, y, label)
        x += width
    y -= 4
    c.setStrokeGray(0.7)
    c.line(margin, y, page_w - margin, y)
    y -= 16

    row_height = 22
    c.setFont("Helvetica", 10)
    for index, name in enumerate(names, 1):
        x = margin
        # Top border for the row (light grid)
        c.setStrokeGray(0.9)
        c.line(margin, y + row_height - 4, page_w - margin, y + row_height - 4)
        # Cell text
        c.drawString(x + 4, y, str(index))
        x += col_widths[0]
        c.drawString(x + 4, y, name[:42])
        x += col_widths[1]
        # P / T / A circles
        for cell_index in range(3):
            c.setStrokeGray(0.5)
            c.circle(x + col_widths[2 + cell_index] / 2, y + 4, 6, stroke=1, fill=0)
            x += col_widths[2 + cell_index]
        if include_time:
            # Underline for handwritten time
            c.setStrokeGray(0.7)
            c.line(x + 4, y - 2, x + col_widths[5] - 4, y - 2)
            x += col_widths[5]
        # Notes underline
        c.setStrokeGray(0.85)
        c.line(x + 4, y - 2, page_w - margin - 4, y - 2)
        y -= row_height
        if y < margin + 60:
            c.showPage()
            y = page_h - margin
            c.setFont("Helvetica", 10)

    # Footer
    c.setFillGray(0.55)
    c.setFont("Helvetica", 7)
    c.drawString(margin, margin / 2,
                 f"PrintWatcher · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.drawRightString(page_w - margin, margin / 2,
                      f"{len(names)} scholar(s)")
    c.showPage()
    c.save()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--class", dest="classname", required=True)
    parser.add_argument("--csv", type=Path, default=None,
                        help="override roster CSV path")
    parser.add_argument("--date", default=None,
                        help="YYYY-MM-DD (default: today)")
    parser.add_argument("--include-time", action="store_true",
                        help="add a Time column for staggered check-in")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--to-inbox", action="store_true",
                        help="drop into PrintWatcher inbox so it auto-prints")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    target_date = date.fromisoformat(args.date) if args.date else date.today()

    try:
        names = load_names(args.classname, args.csv)
    except FileNotFoundError as exc:
        log.error("roster not found: %s", exc)
        return 1
    if not names:
        log.error("roster is empty")
        return 1

    if args.to_inbox:
        output = discover_inbox() / f"attendance-{slugify(args.classname)}-{target_date.isoformat()}.pdf"
    else:
        output = args.out or Path.cwd() / f"attendance-{slugify(args.classname)}-{target_date.isoformat()}.pdf"

    try:
        render(args.classname, names, output, target_date, args.include_time)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 2
    except ImportError:
        log.error("reportlab required: `python -m pip install --user reportlab`")
        return 2
    log.info("wrote %s (%d scholar(s), %s)",
             output, len(names), target_date.isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
