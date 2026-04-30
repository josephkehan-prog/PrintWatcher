"""Combine a scholar's printed work into one chronological portfolio PDF.

Walks history.json for entries where `submitter` matches, locates each
archived file under `_printed/<submitter>/`, then concatenates the PDFs
in the order they were printed. Images (.png/.jpg) are converted to a
PDF page each. Optional cover page summarises totals.

Usage:
    python scripts/student_portfolio.py --submitter MaryDoe
    python scripts/student_portfolio.py --submitter MaryDoe --to-inbox
    python scripts/student_portfolio.py --submitter MaryDoe --last-days 90
    python scripts/student_portfolio.py --submitter MaryDoe \\
        --from 2026-04-01 --to 2026-04-30 --out portfolio.pdf

Dependencies:
    python -m pip install --user pypdf reportlab pillow
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PRINTED_SUBDIR = "_printed"

log = logging.getLogger("printwatcher.portfolio")


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
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read %s: %s", path, exc)
        return []


def filter_records(
    records: list[dict],
    submitter: str,
    date_from: date | None = None,
    date_to: date | None = None,
    only_ok: bool = True,
) -> list[dict]:
    needle = submitter.lower()
    out: list[dict] = []
    for rec in records:
        if (rec.get("submitter") or "").lower() != needle:
            continue
        if only_ok and rec.get("status") != "ok":
            continue
        ts_text = rec.get("timestamp", "")
        try:
            day = datetime.fromisoformat(ts_text).date()
        except (TypeError, ValueError):
            continue
        if date_from and day < date_from:
            continue
        if date_to and day > date_to:
            continue
        out.append(rec)
    out.sort(key=lambda r: r.get("timestamp", ""))
    return out


def find_archived(record: dict, printed_dir: Path) -> Path | None:
    submitter = record.get("submitter") or ""
    filename = record.get("filename") or ""
    if not filename:
        return None
    candidates: list[Path] = []
    if submitter:
        sub_dir = printed_dir / submitter
        if sub_dir.exists():
            candidates.extend(sub_dir.iterdir())
    if printed_dir.exists():
        candidates.extend(printed_dir.iterdir())
    suffix = Path(filename).suffix.lower()
    stem = Path(filename).stem.lower()
    matches = [
        c for c in candidates
        if c.is_file() and c.suffix.lower() == suffix
        and (c.name == filename or c.stem.lower().startswith(stem))
    ]
    if not matches:
        return None
    exact = [m for m in matches if m.name == filename]
    if exact:
        return exact[0]
    return max(matches, key=lambda p: p.stat().st_mtime)


def render_cover(submitter: str, records: list[dict], output: Path) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    page_w, page_h = letter
    c = canvas.Canvas(str(output), pagesize=letter)

    margin = 54
    y = page_h - margin

    c.setFont("Helvetica-Bold", 28)
    c.drawString(margin, y, "Print portfolio")
    y -= 30
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, y, submitter)
    y -= 22
    c.setFont("Helvetica", 11)
    c.setFillGray(0.4)
    if records:
        first_ts = records[0].get("timestamp", "")[:10]
        last_ts = records[-1].get("timestamp", "")[:10]
        c.drawString(margin, y, f"{first_ts} → {last_ts}")
    c.drawString(margin, y - 14, f"{len(records)} item(s) · generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.setFillGray(0)
    y -= 50

    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, "Contents")
    y -= 6
    c.setStrokeGray(0.85)
    c.line(margin, y, page_w - margin, y)
    y -= 16

    c.setFont("Helvetica", 9)
    for index, record in enumerate(records, 1):
        ts = record.get("timestamp", "")[:16].replace("T", " ")
        filename = record.get("filename", "")
        copies = record.get("copies", "")
        line = f"{index:>3}.  {ts:<17} {filename}"
        if copies and str(copies) not in ("1", ""):
            line += f"  ({copies}x)"
        c.drawString(margin, y, line[:130])
        y -= 13
        if y < margin + 30:
            c.showPage()
            y = page_h - margin
            c.setFont("Helvetica", 9)

    c.showPage()
    c.save()


def image_to_pdf(image_path: Path, output: Path) -> None:
    from PIL import Image

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        img.save(output, "PDF", resolution=150.0)


def assemble(records: list[dict], printed_dir: Path, output: Path,
             include_cover: bool, submitter: str) -> int:
    from pypdf import PdfReader, PdfWriter

    output.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    pages_written = 0
    missing = 0

    if include_cover:
        cover_path = output.with_suffix(".cover.pdf")
        render_cover(submitter, records, cover_path)
        try:
            cover_reader = PdfReader(str(cover_path))
            for page in cover_reader.pages:
                writer.add_page(page)
                pages_written += 1
        finally:
            try:
                cover_path.unlink()
            except OSError:
                pass

    for record in records:
        archived = find_archived(record, printed_dir)
        if archived is None:
            missing += 1
            log.warning("missing archive for %s (%s)",
                        record.get("filename", "?"),
                        record.get("timestamp", "?"))
            continue
        if archived.suffix.lower() == ".pdf":
            try:
                reader = PdfReader(str(archived))
            except Exception as exc:
                log.warning("could not read %s: %s", archived.name, exc)
                continue
            for page in reader.pages:
                writer.add_page(page)
                pages_written += 1
        else:
            tmp = output.with_suffix(f".{archived.stem}.tmp.pdf")
            try:
                image_to_pdf(archived, tmp)
                reader = PdfReader(str(tmp))
                for page in reader.pages:
                    writer.add_page(page)
                    pages_written += 1
            except Exception as exc:
                log.warning("could not convert %s: %s", archived.name, exc)
                continue
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass

    with output.open("wb") as fh:
        writer.write(fh)
    if missing:
        log.warning("%d archive file(s) missing — cleaned up since last print?", missing)
    return pages_written


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(name: str) -> str:
    cleaned = _SAFE.sub("_", name.strip()).strip("._")
    return cleaned or "scholar"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--submitter", required=True,
                        help="scholar / submitter name as recorded in history")
    parser.add_argument("--inbox", type=Path, default=None,
                        help="override PrintInbox path")
    parser.add_argument("--history", type=Path, default=None,
                        help="override history.json path")
    parser.add_argument("--from", dest="date_from", help="YYYY-MM-DD inclusive")
    parser.add_argument("--to", dest="date_to", help="YYYY-MM-DD inclusive")
    parser.add_argument("--last-days", type=int, default=None,
                        help="rolling window: today minus N days, inclusive")
    parser.add_argument("--include-errors", action="store_true",
                        help="include failed jobs (off by default)")
    parser.add_argument("--no-cover", action="store_true",
                        help="skip the contents cover page")
    parser.add_argument("--out", type=Path, default=None,
                        help="output PDF path")
    parser.add_argument("--to-inbox", action="store_true",
                        help="drop the portfolio into PrintWatcher inbox")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    inbox = args.inbox or discover_inbox()
    printed_dir = inbox / PRINTED_SUBDIR
    history_path = args.history or default_history_path()

    if not history_path.exists():
        log.error("no history at %s", history_path)
        return 1

    date_from = date.fromisoformat(args.date_from) if args.date_from else None
    date_to = date.fromisoformat(args.date_to) if args.date_to else None
    if args.last_days is not None:
        date_to = date.today()
        date_from = date_to - timedelta(days=args.last_days - 1)

    records = filter_records(
        load_history(history_path),
        args.submitter,
        date_from=date_from, date_to=date_to,
        only_ok=not args.include_errors,
    )
    if not records:
        log.error("no records for %r in the chosen window", args.submitter)
        return 1

    log.info("%s: %d record(s) to assemble", args.submitter, len(records))

    if args.to_inbox:
        output = inbox / f"portfolio-{slugify(args.submitter)}-{date.today().isoformat()}.pdf"
    else:
        output = args.out or Path.cwd() / f"portfolio-{slugify(args.submitter)}.pdf"

    try:
        from pypdf import PdfReader  # noqa: F401
    except ImportError:
        log.error("pypdf required: `python -m pip install --user pypdf reportlab pillow`")
        return 2

    pages = assemble(
        records, printed_dir, output,
        include_cover=not args.no_cover,
        submitter=args.submitter,
    )
    log.info("wrote %s (%d page(s))", output, pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
