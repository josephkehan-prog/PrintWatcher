"""Combine multiple PDFs into one — alphabetically or via a manifest CSV.

Two modes:

    # Alphabetical merge of every PDF in a folder
    python scripts/pdf_merge.py --folder ./student-work --out packet.pdf

    # Manifest-driven order (one filename per line, # for comments)
    python scripts/pdf_merge.py --manifest order.csv --out packet.pdf

    # Drop the merged packet straight into PrintInbox
    python scripts/pdf_merge.py --folder ./student-work --to-inbox

Manifest format — first column is the filename relative to --base-dir
(or the manifest's own directory if --base-dir is omitted). Extra
columns are ignored:

    # student work to print
    Mary-Doe.pdf
    John-Smith.pdf
    Alex-Wong.pdf, optional notes

Dependencies:
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

log = logging.getLogger("printwatcher.pdf_merge")


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


def collect_from_folder(folder: Path) -> list[Path]:
    if not folder.exists():
        raise FileNotFoundError(folder)
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def collect_from_manifest(manifest: Path, base_dir: Path | None) -> list[Path]:
    base = base_dir or manifest.parent
    files: list[Path] = []
    with manifest.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if not row:
                continue
            entry = row[0].strip()
            if not entry or entry.startswith("#"):
                continue
            candidate = (base / entry).resolve()
            if not candidate.exists():
                log.warning("manifest entry missing: %s", entry)
                continue
            files.append(candidate)
    return files


def merge(files: list[Path], output: Path) -> int:
    from pypdf import PdfReader, PdfWriter

    if not files:
        raise ValueError("no input PDFs to merge")
    writer = PdfWriter()
    pages_written = 0
    for path in files:
        try:
            reader = PdfReader(str(path))
        except Exception as exc:  # pragma: no cover - corrupted PDF
            log.warning("skipping %s: %s", path.name, exc)
            continue
        for page in reader.pages:
            writer.add_page(page)
            pages_written += 1
        log.info("merged %s (%d pages)", path.name, len(reader.pages))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as fh:
        writer.write(fh)
    return pages_written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--folder", type=Path, help="merge all PDFs in this folder alphabetically")
    source.add_argument("--manifest", type=Path, help="CSV listing PDFs to merge in order")
    parser.add_argument("--base-dir", type=Path, default=None,
                        help="base directory for relative paths in the manifest")
    parser.add_argument("--out", type=Path, default=None, help="output PDF path")
    parser.add_argument("--to-inbox", action="store_true",
                        help="write the merged PDF into the PrintWatcher inbox")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.folder:
        files = collect_from_folder(args.folder)
        default_name = f"{args.folder.name}-merged.pdf"
    else:
        files = collect_from_manifest(args.manifest, args.base_dir)
        default_name = f"{args.manifest.stem}-merged.pdf"

    if args.to_inbox and args.out is not None:
        parser.error("--to-inbox and --out are mutually exclusive")
    if args.to_inbox:
        output = discover_inbox() / default_name
    else:
        output = args.out or Path.cwd() / default_name

    log.info("merging %d file(s) -> %s", len(files), output)
    pages = merge(files, output)
    log.info("done: %d pages in %s", pages, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
