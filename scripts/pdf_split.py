"""Split a PDF by page-range expressions.

Different from `roster_split.py` (which splits a packet into N equal
parts driven by a roster CSV). This one accepts arbitrary page ranges:

    python scripts/pdf_split.py packet.pdf --pages "1-5"           -> 5-page PDF
    python scripts/pdf_split.py packet.pdf --pages "1,3,7-10"      -> 5 selected pages
    python scripts/pdf_split.py packet.pdf --pages "10-"           -> page 10 to end

Or split into multiple labelled files in one call:

    python scripts/pdf_split.py packet.pdf --segments \\
        "1-5:cover, 6-10:body, 11-:appendix"

Each segment becomes its own PDF (`<input-stem>-<label>.pdf`).

`--to-inbox` drops every output into PrintWatcher's inbox.

Dependencies:
    python -m pip install --user pypdf
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

log = logging.getLogger("printwatcher.pdf_split")


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


def parse_ranges(spec: str, total_pages: int) -> list[int]:
    """Convert a `1-3,5,8-` style spec into a sorted list of 1-based page indices."""
    if not spec.strip():
        return []
    indices: set[int] = set()
    for chunk in spec.split(","):
        token = chunk.strip()
        if not token:
            continue
        if "-" in token:
            start_str, _, end_str = token.partition("-")
            start = int(start_str) if start_str else 1
            end = int(end_str) if end_str else total_pages
            if start < 1 or end > total_pages or start > end:
                raise ValueError(
                    f"range {token!r} out of bounds (1-{total_pages})"
                )
            indices.update(range(start, end + 1))
        else:
            page = int(token)
            if page < 1 or page > total_pages:
                raise ValueError(f"page {page} out of bounds (1-{total_pages})")
            indices.add(page)
    return sorted(indices)


def parse_segments(spec: str) -> list[tuple[str, str]]:
    """Convert `1-5:cover, 6-10:body` into [(range, label)] pairs."""
    pairs: list[tuple[str, str]] = []
    for chunk in spec.split(","):
        token = chunk.strip()
        if not token:
            continue
        if ":" not in token:
            raise ValueError(f"segment {token!r} missing label (expected `range:label`)")
        range_part, label = token.split(":", 1)
        pairs.append((range_part.strip(), label.strip()))
    return pairs


_SAFE_LABEL = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(label: str) -> str:
    cleaned = _SAFE_LABEL.sub("_", label.strip()).strip("._")
    return cleaned or "segment"


def write_subset(reader, indices: list[int], output: Path) -> None:
    from pypdf import PdfWriter

    output.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for page_num in indices:
        writer.add_page(reader.pages[page_num - 1])
    with output.open("wb") as fh:
        writer.write(fh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="source PDF")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pages", help="page range expression for a single output, e.g. '1-5,8'")
    group.add_argument("--segments",
                       help="multiple `range:label` pairs separated by commas")
    parser.add_argument("-o", "--out", type=Path, default=None,
                        help="output path (single mode) or output directory (segments mode)")
    parser.add_argument("--to-inbox", action="store_true",
                        help="write outputs into PrintWatcher's inbox")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.input.exists():
        parser.error(f"input not found: {args.input}")

    try:
        from pypdf import PdfReader
    except ImportError:
        log.error("pypdf not installed — `python -m pip install --user pypdf`")
        return 2

    reader = PdfReader(str(args.input))
    total = len(reader.pages)

    if args.pages:
        try:
            indices = parse_ranges(args.pages, total)
        except ValueError as exc:
            log.error("%s", exc)
            return 1
        if not indices:
            log.error("no pages selected")
            return 1
        if args.to_inbox:
            output = discover_inbox() / f"{args.input.stem}-extract.pdf"
        elif args.out:
            output = args.out
        else:
            output = args.input.with_name(f"{args.input.stem}-extract.pdf")
        write_subset(reader, indices, output)
        log.info("wrote %s (%d page(s))", output, len(indices))
        return 0

    # Segments mode
    try:
        segments = parse_segments(args.segments)
    except ValueError as exc:
        log.error("%s", exc)
        return 1

    if args.to_inbox:
        output_dir = discover_inbox()
    elif args.out:
        output_dir = args.out
    else:
        output_dir = args.input.parent

    output_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for range_spec, label in segments:
        try:
            indices = parse_ranges(range_spec, total)
        except ValueError as exc:
            log.error("segment %r: %s", label, exc)
            failures += 1
            continue
        if not indices:
            log.warning("segment %r produced no pages, skipping", label)
            continue
        target = output_dir / f"{args.input.stem}-{slugify(label)}.pdf"
        write_subset(reader, indices, target)
        log.info("wrote %s (%d page(s))", target.name, len(indices))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
