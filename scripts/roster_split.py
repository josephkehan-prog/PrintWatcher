"""Split a multi-page PDF into one PDF per roster row.

Usage:
    python scripts/roster_split.py --pdf packet.pdf --roster roster.csv --out ./out

    # automatic pages-per-student (total pages / roster rows):
    python scripts/roster_split.py --pdf packet.pdf --roster roster.csv --out ./out

    # explicit pages per student:
    python scripts/roster_split.py --pdf packet.pdf --roster roster.csv --out ./out --pages-per-student 2

    # send each split straight to the watcher inbox:
    python scripts/roster_split.py --pdf packet.pdf --roster roster.csv --to-inbox

CSV format — first column is the name, additional columns are ignored:

    name
    Mary Doe
    John Smith
    Alex Wong

Output filenames: "<row>-<safe-name>.pdf" (zero-padded row index keeps
file order stable in Explorer / OneDrive).

Dependencies (install once):
    python -m pip install --user pypdf
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
from pathlib import Path

log = logging.getLogger("printwatcher.roster_split")


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


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", name.strip())
    return cleaned.strip("._") or "row"


def load_names(roster_path: Path) -> list[str]:
    with roster_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    if not rows:
        return []
    # If first row looks like a header, skip it
    header_candidates = {"name", "student", "students"}
    if rows[0] and rows[0][0].strip().lower() in header_candidates:
        rows = rows[1:]
    return [row[0].strip() for row in rows if row and row[0].strip()]


def split_pdf(
    source: Path,
    names: list[str],
    output_dir: Path,
    pages_per_student: int | None,
) -> list[Path]:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    total_pages = len(reader.pages)
    if not names:
        raise ValueError("roster is empty")

    if pages_per_student is None:
        if total_pages % len(names) != 0:
            raise ValueError(
                f"cannot infer pages-per-student: {total_pages} pages / {len(names)} "
                f"students leaves a remainder. Pass --pages-per-student explicitly."
            )
        pages_per_student = total_pages // len(names)

    expected_pages = pages_per_student * len(names)
    if expected_pages > total_pages:
        raise ValueError(
            f"need {expected_pages} pages but PDF only has {total_pages}"
        )
    if expected_pages < total_pages:
        log.warning(
            "ignoring %d trailing pages beyond the roster",
            total_pages - expected_pages,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    width = max(2, len(str(len(names))))
    for idx, name in enumerate(names, start=1):
        writer = PdfWriter()
        start = (idx - 1) * pages_per_student
        for offset in range(pages_per_student):
            writer.add_page(reader.pages[start + offset])
        target = output_dir / f"{idx:0{width}d}-{slugify(name)}.pdf"
        with target.open("wb") as fh:
            writer.write(fh)
        written.append(target)
        log.info("wrote %s (%d pages)", target.name, pages_per_student)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", required=True, type=Path, help="source packet PDF")
    parser.add_argument("--roster", required=True, type=Path,
                        help="CSV of student names (first column)")
    parser.add_argument("--out", type=Path, default=None,
                        help="output directory (default: <pdf-name>-split/)")
    parser.add_argument("--pages-per-student", type=int, default=None,
                        help="how many pages per student; inferred if omitted")
    parser.add_argument("--to-inbox", action="store_true",
                        help="write outputs directly into the PrintWatcher inbox")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.pdf.exists():
        parser.error(f"PDF not found: {args.pdf}")
    if not args.roster.exists():
        parser.error(f"roster not found: {args.roster}")

    if args.to_inbox:
        if args.out is not None:
            parser.error("--to-inbox and --out are mutually exclusive")
        output_dir = discover_inbox()
    else:
        output_dir = args.out or args.pdf.parent / f"{args.pdf.stem}-split"

    names = load_names(args.roster)
    log.info("roster: %d students", len(names))

    try:
        written = split_pdf(args.pdf, names, output_dir, args.pages_per_student)
    except ValueError as exc:
        log.error("%s", exc)
        return 1

    log.info("done: %d files in %s", len(written), output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
