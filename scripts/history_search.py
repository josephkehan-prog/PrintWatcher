"""Search %APPDATA%/PrintWatcher/history.json from the terminal.

Beyond what the History tab's filter box can do — supports regex,
date ranges, status / submitter / printer filters, and JSON output for
piping into other tools.

Examples:

    python scripts/history_search.py --query "quiz"
    python scripts/history_search.py --regex "(?i)report\\d+"
    python scripts/history_search.py --status error --last-days 7
    python scripts/history_search.py --submitter MaryDoe --json
    python scripts/history_search.py --from 2026-04-01 --to 2026-04-30 \\
        --printer Printix --csv out.csv

Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

log = logging.getLogger("printwatcher.history_search")


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


def _parse_iso_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def filter_records(
    records: list[dict],
    *,
    query: str | None = None,
    regex: str | None = None,
    status: str | None = None,
    submitter: str | None = None,
    printer: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    pattern = re.compile(regex) if regex else None
    out: list[dict] = []
    for rec in records:
        ts = _parse_iso_ts(rec.get("timestamp", ""))
        if date_from and (ts is None or ts.date() < date_from):
            continue
        if date_to and (ts is None or ts.date() > date_to):
            continue
        if status and rec.get("status", "").lower() != status.lower():
            continue
        if submitter and submitter.lower() not in (rec.get("submitter") or "").lower():
            continue
        if printer and printer.lower() not in (rec.get("printer") or "").lower():
            continue
        if query:
            haystack = " ".join((
                rec.get("filename", ""), rec.get("submitter", ""),
                rec.get("printer", ""), rec.get("status", ""),
                rec.get("detail", ""),
            )).lower()
            if query.lower() not in haystack:
                continue
        if pattern:
            haystack = " ".join((
                rec.get("filename", ""), rec.get("submitter", ""),
                rec.get("printer", ""), rec.get("status", ""),
                rec.get("detail", ""),
            ))
            if not pattern.search(haystack):
                continue
        out.append(rec)
    return out


def render_table(records: list[dict]) -> str:
    if not records:
        return "(no matches)"
    rows = [
        (
            rec.get("timestamp", "")[:16].replace("T", " "),
            rec.get("submitter") or "—",
            rec.get("filename") or "—",
            rec.get("status") or "—",
            str(rec.get("copies") or 1),
            rec.get("printer") or "—",
        )
        for rec in records
    ]
    headers = ("Time", "Submitter", "File", "Status", "Cp", "Printer")
    widths = [
        max(len(h), max(len(row[i]) for row in rows))
        for i, h in enumerate(headers)
    ]
    widths = [min(w, 60) for w in widths]
    lines = []
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines.append(fmt.format(*headers))
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        truncated = tuple(
            (cell[: widths[i] - 1] + "…") if len(cell) > widths[i] else cell
            for i, cell in enumerate(row)
        )
        lines.append(fmt.format(*truncated))
    return "\n".join(lines)


def write_csv(records: list[dict], path: Path) -> None:
    if not records:
        path.write_text("(no records)\n", encoding="utf-8")
        return
    fieldnames = sorted({key for rec in records for key in rec.keys()})
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--history", type=Path, default=None,
                        help="override history.json path")
    parser.add_argument("--query", help="case-insensitive substring across all fields")
    parser.add_argument("--regex", help="Python regex; whole record fields concatenated")
    parser.add_argument("--status", choices=("ok", "error"))
    parser.add_argument("--submitter", help="substring match against submitter")
    parser.add_argument("--printer", help="substring match against printer")
    parser.add_argument("--from", dest="date_from", help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--to", dest="date_to", help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--last-days", type=int, default=None,
                        help="rolling window: today minus N days, inclusive")
    parser.add_argument("--json", action="store_true",
                        help="emit JSON (one record per line)")
    parser.add_argument("--csv", type=Path, default=None,
                        help="also write the matching records to this CSV")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap output to this many rows (newest first)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    history_path = args.history or default_history_path()
    if not history_path.exists():
        log.error("no history at %s", history_path)
        return 1

    records = load_history(history_path)

    date_from = date.fromisoformat(args.date_from) if args.date_from else None
    date_to = date.fromisoformat(args.date_to) if args.date_to else None
    if args.last_days is not None:
        date_to = date.today()
        date_from = date_to - timedelta(days=args.last_days - 1)

    matched = filter_records(
        records,
        query=args.query,
        regex=args.regex,
        status=args.status,
        submitter=args.submitter,
        printer=args.printer,
        date_from=date_from,
        date_to=date_to,
    )

    matched.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    if args.limit:
        matched = matched[:args.limit]

    if args.csv:
        write_csv(matched, args.csv)
        log.info("csv: %s (%d row(s))", args.csv, len(matched))

    if args.json:
        for rec in matched:
            print(json.dumps(rec, ensure_ascii=False))
    else:
        print(render_table(matched))
        print()
        print(f"  matched {len(matched)} of {len(records)} record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
