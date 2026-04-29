"""One-page summary of recent print activity, rendered to PDF.

Reads `%APPDATA%\\PrintWatcher\\history.json` (or `--history`), filters by
date range (default: this Mon-Fri ISO week), and renders a one-page PDF
showing totals, by-submitter, by-printer, errors, and the busiest day.

Usage:
    python scripts/weekly_report.py
    python scripts/weekly_report.py --to-inbox       # auto-print via the watcher
    python scripts/weekly_report.py --from 2026-04-22 --to 2026-04-28
    python scripts/weekly_report.py --last-days 30 --out report.pdf
    python scripts/weekly_report.py --csv export.csv # also dump filtered rows

Dependencies:
    python -m pip install --user reportlab
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

log = logging.getLogger("printwatcher.report")


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


def default_history_path() -> Path:
    base = os.environ.get("APPDATA")
    return (
        Path(base) / "PrintWatcher" / "history.json"
        if base else Path.home() / ".printwatcher" / "history.json"
    )


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read %s: %s", path, exc)
        return []
    return data if isinstance(data, list) else []


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def filter_window(records: list[dict], start: date, end: date) -> list[dict]:
    out: list[dict] = []
    for rec in records:
        ts = _parse_ts(rec.get("timestamp", ""))
        if ts is None:
            continue
        if start <= ts.date() <= end:
            out.append(rec)
    return out


def iso_week_window(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def aggregate(records: list[dict]) -> dict:
    totals = {
        "total": len(records),
        "ok": sum(1 for r in records if r.get("status") == "ok"),
        "errors": sum(1 for r in records if r.get("status") == "error"),
    }
    pages_estimate = sum(int(r.get("copies", 1) or 1) for r in records)
    by_submitter = Counter(r.get("submitter") or "—" for r in records)
    by_printer = Counter(r.get("printer") or "—" for r in records)
    by_status = Counter(r.get("status") or "—" for r in records)

    by_day: defaultdict[str, int] = defaultdict(int)
    for rec in records:
        ts = _parse_ts(rec.get("timestamp", ""))
        if ts is None:
            continue
        by_day[ts.strftime("%a %b %d")] += 1
    busiest = max(by_day.items(), key=lambda kv: kv[1]) if by_day else ("—", 0)

    return {
        "totals": totals,
        "pages_estimate": pages_estimate,
        "by_submitter": by_submitter.most_common(10),
        "by_printer": by_printer.most_common(10),
        "by_status": by_status.most_common(),
        "by_day": sorted(by_day.items()),
        "busiest": busiest,
    }


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

def render_report(stats: dict, start: date, end: date, output: Path) -> None:
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

    margin = 54
    y = page_h - margin

    c.setFont("Helvetica-Bold", 24)
    c.drawString(margin, y, "PrintWatcher · weekly report")
    y -= 22
    c.setFont("Helvetica", 11)
    c.setFillGray(0.4)
    c.drawString(
        margin, y,
        f"{start.strftime('%a %b %d, %Y')} → {end.strftime('%a %b %d, %Y')} "
        f"· generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    )
    c.setFillGray(0)
    y -= 36

    # Top stat tiles
    tiles = (
        ("Total prints", str(stats["totals"]["total"])),
        ("Pages (≈)", str(stats["pages_estimate"])),
        ("Errors", str(stats["totals"]["errors"])),
        ("Busiest day", f"{stats['busiest'][0]}  ·  {stats['busiest'][1]}"),
    )
    tile_w = (page_w - margin * 2 - 30) / 4
    for i, (label, value) in enumerate(tiles):
        x = margin + i * (tile_w + 10)
        c.setFillGray(0.96)
        c.roundRect(x, y - 64, tile_w, 64, 8, fill=1, stroke=0)
        c.setFillGray(0.45)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x + 12, y - 22, label.upper())
        c.setFillGray(0.1)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x + 12, y - 50, value)
    y -= 90

    def draw_section(title: str, rows: list[tuple[str, int]],
                     bar_max: int | None = None) -> None:
        nonlocal y
        c.setFillGray(0.1)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(margin, y, title)
        y -= 14
        c.setStrokeGray(0.85)
        c.line(margin, y, page_w - margin, y)
        y -= 14
        if not rows:
            c.setFillGray(0.5)
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(margin, y, "(no data)")
            y -= 18
            return
        max_count = bar_max or max(count for _, count in rows) or 1
        c.setFont("Helvetica", 10)
        for label, count in rows:
            label_text = label[:36] + "…" if len(label) > 36 else label
            c.setFillGray(0.15)
            c.drawString(margin, y, label_text)
            c.drawRightString(page_w - margin, y, str(count))
            bar_w = ((page_w - margin * 2 - 200) * count / max_count)
            c.setFillGray(0.85)
            c.rect(margin + 200, y - 2, bar_w, 6, fill=1, stroke=0)
            c.setFillGray(0.15)
            y -= 16
        y -= 6

    draw_section("By submitter (top 10)", stats["by_submitter"])
    draw_section("By printer (top 10)", stats["by_printer"])
    draw_section("By status",
                 [(label.upper(), count) for label, count in stats["by_status"]])
    draw_section("Per day", stats["by_day"])

    # Footer
    c.setFillGray(0.5)
    c.setFont("Helvetica", 8)
    c.drawString(margin, margin / 2, "PrintWatcher")
    c.drawRightString(
        page_w - margin, margin / 2,
        f"history: {default_history_path()}",
    )
    c.showPage()
    c.save()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--history", type=Path, default=None,
                        help="override history.json path")
    parser.add_argument("--from", dest="date_from", type=str, default=None,
                        help="start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", type=str, default=None,
                        help="end date (YYYY-MM-DD)")
    parser.add_argument("--last-days", type=int, default=None,
                        help="rolling window N days back from today")
    parser.add_argument("--out", type=Path, default=None,
                        help="output PDF path")
    parser.add_argument("--to-inbox", action="store_true",
                        help="drop the report into PrintInbox so it auto-prints")
    parser.add_argument("--csv", type=Path, default=None,
                        help="also dump the filtered records to this CSV")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    history_path = args.history or default_history_path()
    log.info("history: %s", history_path)
    records = load_history(history_path)

    if args.last_days is not None:
        end = date.today()
        start = end - timedelta(days=args.last_days - 1)
    elif args.date_from or args.date_to:
        start = (
            date.fromisoformat(args.date_from) if args.date_from
            else date.today() - timedelta(days=6)
        )
        end = date.fromisoformat(args.date_to) if args.date_to else date.today()
    else:
        start, end = iso_week_window()

    log.info("window: %s → %s", start.isoformat(), end.isoformat())
    filtered = filter_window(records, start, end)
    log.info("records in window: %d", len(filtered))

    if args.csv:
        with args.csv.open("w", encoding="utf-8", newline="") as fh:
            if filtered:
                writer = csv.DictWriter(fh, fieldnames=list(filtered[0].keys()))
                writer.writeheader()
                writer.writerows(filtered)
            else:
                fh.write("(no records)\n")
        log.info("csv: %s", args.csv)

    stats = aggregate(filtered)

    if args.to_inbox:
        output = discover_inbox() / f"PrintWatcher-report-{start.isoformat()}_{end.isoformat()}.pdf"
    elif args.out:
        output = args.out
    else:
        output = Path.cwd() / f"printwatcher-report-{start.isoformat()}_{end.isoformat()}.pdf"

    try:
        render_report(stats, start, end, output)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 2
    log.info("wrote %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
