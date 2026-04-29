"""Inspect a PDF and report what's inside before you print it.

Usage:
    python scripts/pdf_inspect.py packet.pdf
    python scripts/pdf_inspect.py packet.pdf --json
    python scripts/pdf_inspect.py *.pdf

Reports per file: page count, dimensions of each unique page size, total
estimated paper sheets (assuming single-sided), file size, embedded fonts,
whether pages contain raster images, encryption flag, and PDF version.

Useful as a pre-flight check before printing 200-page packets.

Dependencies (install once):
    python -m pip install --user pypdf
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

log = logging.getLogger("printwatcher.pdf_inspect")


def _format_size(num_bytes: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def _format_dim(width: float, height: float) -> str:
    """Convert PDF points to inches and a friendly label."""
    in_w = width / 72
    in_h = height / 72
    label = ""
    if 8.4 <= in_w <= 8.6 and 10.9 <= in_h <= 11.1:
        label = "Letter"
    elif 8.2 <= in_w <= 8.3 and 11.6 <= in_h <= 11.8:
        label = "A4"
    elif 8.4 <= in_w <= 8.6 and 13.9 <= in_h <= 14.1:
        label = "Legal"
    elif 5.7 <= in_w <= 5.9 and 8.2 <= in_w <= 8.4:
        label = "A5"
    return f"{in_w:.2f} x {in_h:.2f} in" + (f" ({label})" if label else "")


def inspect(path: Path) -> dict:
    from pypdf import PdfReader

    record: dict = {
        "path": str(path),
        "size": _format_size(path.stat().st_size),
        "size_bytes": path.stat().st_size,
        "error": None,
    }
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pragma: no cover - PDF parse failure
        record["error"] = f"failed to open: {exc}"
        return record

    record["pdf_version"] = reader.pdf_header[5:] if reader.pdf_header else "?"
    record["encrypted"] = bool(reader.is_encrypted)
    record["pages"] = len(reader.pages)

    sizes: Counter[tuple[float, float]] = Counter()
    has_images = False
    fonts: set[str] = set()
    for page in reader.pages:
        try:
            box = page.mediabox
            sizes[(round(float(box.width), 1), round(float(box.height), 1))] += 1
        except Exception:
            pass
        try:
            resources = page.get("/Resources") or {}
            xobjects = resources.get("/XObject") or {}
            for obj in xobjects.values():
                obj_data = obj.get_object()
                if obj_data.get("/Subtype") == "/Image":
                    has_images = True
                    break
            font_dict = resources.get("/Font") or {}
            for font in font_dict.values():
                font_obj = font.get_object()
                base = font_obj.get("/BaseFont")
                if base:
                    fonts.add(str(base).lstrip("/"))
        except Exception:
            pass

    record["has_images"] = has_images
    record["fonts"] = sorted(fonts)
    record["page_sizes"] = [
        {"size": _format_dim(w, h), "count": count}
        for (w, h), count in sizes.most_common()
    ]
    record["sheets_simplex"] = record["pages"]
    record["sheets_duplex"] = (record["pages"] + 1) // 2
    return record


def render_text(record: dict) -> str:
    lines: list[str] = []
    lines.append(record["path"])
    lines.append("-" * len(record["path"]))
    if record.get("error"):
        lines.append(f"  ERROR: {record['error']}")
        return "\n".join(lines)
    lines.append(f"  size           {record['size']}")
    lines.append(f"  pdf version    {record['pdf_version']}")
    lines.append(f"  encrypted      {record['encrypted']}")
    lines.append(f"  pages          {record['pages']}")
    lines.append(f"  paper (simplex){record['sheets_simplex']:>5}")
    lines.append(f"  paper (duplex) {record['sheets_duplex']:>5}")
    lines.append(f"  has images     {record['has_images']}")
    lines.append(f"  page sizes:")
    for entry in record["page_sizes"]:
        lines.append(f"    {entry['count']:>4} x  {entry['size']}")
    if record["fonts"]:
        lines.append(f"  fonts ({len(record['fonts'])}):")
        for f in record["fonts"][:10]:
            lines.append(f"    {f}")
        if len(record["fonts"]) > 10:
            lines.append(f"    ... and {len(record['fonts']) - 10} more")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="PDF files to inspect")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    records = [inspect(p) for p in args.paths if p.exists()]
    if args.json:
        print(json.dumps(records, indent=2))
        return 1 if any(r.get("error") for r in records) else 0
    for record in records:
        print(render_text(record))
        print()
    return 1 if any(r.get("error") for r in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
