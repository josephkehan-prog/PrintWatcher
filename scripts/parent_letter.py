"""Mail-merge personalised parent letters from a roster CSV + text template.

Template uses Python ``string.Template`` syntax with ``${field}``
placeholders. Every column from the roster CSV is available — the
defaults for the Classical roster format mean ``${first}``, ``${last}``,
``${reading_level}``, ``${ela_avg}``, etc. all resolve.

Two output modes:

    # one PDF per scholar in the chosen folder
    python scripts/parent_letter.py --class Hamilton --template letter.txt \\
        --out ./letters

    # all letters merged into a single PDF (also fine to print as-is)
    python scripts/parent_letter.py --class Hamilton --template letter.txt \\
        --merged --out hamilton-letters.pdf

    # straight to PrintWatcher
    python scripts/parent_letter.py --class Hamilton --template letter.txt \\
        --merged --to-inbox

Template file example::

    Dear ${parent_name},

    This is a quarterly update for ${first} ${last}. ${first} is
    currently reading at level ${reading_level} and is averaging
    ${ela_avg} in ELA and ${math_avg} in Math.

    Please reach out with any questions.

    — Mr. Han, Hamilton classroom

Missing fields render as empty strings (``string.Template.safe_substitute``).
Use ``--strict`` to fail loudly on a missing key instead.

Dependencies:
    python -m pip install --user reportlab pypdf
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from string import Template

log = logging.getLogger("printwatcher.parent_letter")


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


def load_roster(class_name: str, override: Path | None) -> list[dict]:
    path = override or (rosters_dir() / f"{slugify(class_name)}.csv")
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [
            {k: (v or "").strip() for k, v in row.items() if k}
            for row in reader
            if (row.get("name") or "").strip()
        ]


def render_text(template_text: str, row: dict, strict: bool) -> str:
    template = Template(template_text)
    if strict:
        return template.substitute(row)
    return template.safe_substitute(row)


def render_letter_pdf(text: str, output: Path) -> None:
    """Render a plain text letter as a PDF page (Letter, 11pt)."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    output.parent.mkdir(parents=True, exist_ok=True)
    page_w, page_h = letter
    c = canvas.Canvas(str(output), pagesize=letter)
    margin_x = 72
    margin_y = 72
    width = page_w - 2 * margin_x

    text_obj = c.beginText(margin_x, page_h - margin_y)
    text_obj.setFont("Helvetica", 11)
    text_obj.setLeading(15)

    for paragraph in text.split("\n"):
        if not paragraph.strip():
            text_obj.textLine("")
            continue
        # Naive word-wrap to respect the page width
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = (current + " " + word).strip() if current else word
            if c.stringWidth(candidate, "Helvetica", 11) <= width:
                current = candidate
            else:
                text_obj.textLine(current)
                current = word
        if current:
            text_obj.textLine(current)

    c.drawText(text_obj)
    c.setFillGray(0.55)
    c.setFont("Helvetica", 8)
    c.drawString(margin_x, margin_y / 2,
                 f"PrintWatcher · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.showPage()
    c.save()


def merge_pdfs(parts: list[Path], output: Path) -> int:
    from pypdf import PdfReader, PdfWriter

    output.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    pages = 0
    for path in parts:
        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            log.warning("skip %s: %s", path.name, exc)
            continue
        for page in reader.pages:
            writer.add_page(page)
            pages += 1
    with output.open("wb") as fh:
        writer.write(fh)
    return pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--class", dest="classname", required=True,
                        help="roster class name (the CSV in %%APPDATA%%/PrintWatcher/rosters/)")
    parser.add_argument("--template", type=Path, required=True,
                        help="text template with ${field} placeholders")
    parser.add_argument("--csv", type=Path, default=None,
                        help="override roster CSV path (skips rosters_dir lookup)")
    parser.add_argument("--out", type=Path, default=None,
                        help="output folder (default mode) or PDF path (with --merged)")
    parser.add_argument("--merged", action="store_true",
                        help="emit a single combined PDF instead of one per scholar")
    parser.add_argument("--to-inbox", action="store_true",
                        help="write outputs into PrintWatcher inbox")
    parser.add_argument("--strict", action="store_true",
                        help="fail if a template field is missing in the roster row")
    parser.add_argument("--filename-field", default="name",
                        help="roster column used for per-scholar filename (default: name)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.template.exists():
        parser.error(f"template not found: {args.template}")
    template_text = args.template.read_text(encoding="utf-8")

    try:
        roster = load_roster(args.classname, args.csv)
    except FileNotFoundError as exc:
        log.error("roster not found: %s", exc)
        return 1
    if not roster:
        log.error("roster is empty")
        return 1

    log.info("class %s: %d scholar(s)", args.classname, len(roster))

    if args.merged:
        if args.to_inbox:
            output = discover_inbox() / f"{slugify(args.classname)}-letters-{date.today().isoformat()}.pdf"
        else:
            output = args.out or Path.cwd() / f"{slugify(args.classname)}-letters.pdf"
    else:
        output = (
            discover_inbox() if args.to_inbox
            else (args.out or Path.cwd() / f"{slugify(args.classname)}-letters")
        )

    try:
        from reportlab.pdfgen import canvas  # noqa: F401  -- import early
    except ImportError:
        log.error("reportlab required: `python -m pip install --user reportlab pypdf`")
        return 2

    parts: list[Path] = []
    failures = 0

    for index, row in enumerate(roster, 1):
        try:
            text = render_text(template_text, row, args.strict)
        except KeyError as exc:
            log.error("scholar #%d (%s): missing template field %s",
                      index, row.get("name", "?"), exc)
            failures += 1
            continue

        filename_source = (row.get(args.filename_field) or row.get("name") or f"scholar-{index}").strip()
        target_dir = output if (not args.merged and args.to_inbox) else None
        if args.merged:
            target = (output.parent / f"{output.stem}-{index:03d}-{slugify(filename_source)}.tmp.pdf")
        else:
            base = output if not args.to_inbox else discover_inbox()
            base.mkdir(parents=True, exist_ok=True)
            target = base / f"{index:03d}-{slugify(filename_source)}.pdf"
        render_letter_pdf(text, target)
        parts.append(target)
        log.info("wrote %s", target.name)

    if args.merged:
        try:
            from pypdf import PdfReader  # noqa: F401
        except ImportError:
            log.error("pypdf required when --merged: `python -m pip install --user pypdf`")
            return 2
        pages = merge_pdfs(parts, output)
        for tmp in parts:
            try:
                tmp.unlink()
            except OSError:
                pass
        log.info("merged %d letter(s) (%d page(s)) into %s",
                 len(parts), pages, output)
    else:
        log.info("done: %d letter(s) in %s", len(parts), output)

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
