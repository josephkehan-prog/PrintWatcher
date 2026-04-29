"""Scholar roster CLI — manage class rosters and drive the rest of the toolkit.

Storage: %APPDATA%/PrintWatcher/rosters/<class>.csv (one CSV per class,
single column 'name' plus any optional metadata columns the teacher
adds; extras are preserved on rewrite).

Subcommands:

    roster classes                                list every roster
    roster init <class>                           create an empty roster
    roster add <class> "<name>"                   append a scholar
    roster remove <class> "<name>"                drop a scholar
    roster rename <class> "<old>" "<new>"         rename in place
    roster list <class>                           print roster
    roster import <class> <file>                  one name per line
    roster export <class> [--out roster.csv]      dump as CSV
    roster folders <class> [--prefix] [--clean]   per-student subfolders
                                                   in PrintInbox
    roster sheet <class> [--to-inbox]             printable class list PDF
    roster nametags <class> [--per-page N]        name-tags grid PDF
    roster groups <class> --size N [--seed N]     random group assignments
    roster split <class> <packet.pdf> [...]       wraps roster_split.py
    roster stamp <class> <worksheet.pdf>          per-scholar stamped PDFs

PDF generation requires `reportlab` (and `pypdf` for stamp).
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import os
import random
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

log = logging.getLogger("printwatcher.roster")


# ---------------------------------------------------------------------------
# Path discovery
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Roster I/O
# ---------------------------------------------------------------------------

_SAFE_FILE = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(name: str) -> str:
    cleaned = _SAFE_FILE.sub("_", name.strip())
    return cleaned.strip("._") or "scholar"


def class_path(class_name: str) -> Path:
    return rosters_dir() / f"{slugify(class_name)}.csv"


def list_classes() -> list[Path]:
    if not rosters_dir().exists():
        return []
    return sorted(p for p in rosters_dir().iterdir() if p.suffix == ".csv")


def read_roster(path: Path) -> tuple[list[str], list[dict]]:
    """Return (header columns, rows). First column is always 'name'."""
    if not path.exists():
        return ["name"], []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = [row for row in reader if (row.get("name") or "").strip()]
        header = reader.fieldnames or ["name"]
    if "name" not in header:
        header = ["name"] + [h for h in header if h != "name"]
    return header, rows


def write_roster(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if "name" not in header:
        header = ["name"] + header
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in header})


def names_only(rows: list[dict]) -> list[str]:
    return [r["name"].strip() for r in rows if r.get("name", "").strip()]


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_classes(args: argparse.Namespace) -> int:
    classes = list_classes()
    if not classes:
        log.info("no rosters in %s", rosters_dir())
        return 0
    log.info("rosters in %s:", rosters_dir())
    for path in classes:
        _header, rows = read_roster(path)
        log.info("  %s  (%d scholars)", path.stem, len(rows))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    if path.exists():
        log.error("roster already exists: %s", path)
        return 1
    write_roster(path, ["name"], [])
    log.info("created %s", path)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    header, rows = read_roster(path)
    name = args.name.strip()
    if not name:
        log.error("name is empty")
        return 2
    if any(r["name"].strip().lower() == name.lower() for r in rows):
        log.warning("%s is already on the roster", name)
        return 0
    rows.append({"name": name})
    write_roster(path, header, rows)
    log.info("added %s to %s (%d total)", name, args.classname, len(rows))
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    header, rows = read_roster(path)
    name = args.name.strip()
    survivors = [r for r in rows if r["name"].strip().lower() != name.lower()]
    if len(survivors) == len(rows):
        log.warning("%s not found on %s", name, args.classname)
        return 1
    write_roster(path, header, survivors)
    log.info("removed %s from %s (%d remain)", name, args.classname, len(survivors))
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    header, rows = read_roster(path)
    old = args.old.strip().lower()
    new = args.new.strip()
    found = False
    for row in rows:
        if row["name"].strip().lower() == old:
            row["name"] = new
            found = True
    if not found:
        log.warning("%s not found on %s", args.old, args.classname)
        return 1
    write_roster(path, header, rows)
    log.info("renamed %s -> %s", args.old, new)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    if not path.exists():
        log.error("no roster for %s", args.classname)
        return 1
    _header, rows = read_roster(path)
    log.info("%s (%d scholars):", args.classname, len(rows))
    for i, row in enumerate(rows, 1):
        log.info("  %2d. %s", i, row["name"])
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    if not args.file.exists():
        log.error("file not found: %s", args.file)
        return 1
    header, rows = read_roster(path)
    existing = {r["name"].strip().lower() for r in rows}
    added = 0
    for raw in args.file.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # first column if comma-delimited
        line = line.split(",")[0].strip()
        if not line or line.lower() in existing:
            continue
        rows.append({"name": line})
        existing.add(line.lower())
        added += 1
    write_roster(path, header, rows)
    log.info("imported %d new scholar(s); roster has %d total", added, len(rows))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    if not path.exists():
        log.error("no roster for %s", args.classname)
        return 1
    out = args.out or Path.cwd() / f"{slugify(args.classname)}.csv"
    shutil.copy2(path, out)
    log.info("wrote %s", out)
    return 0


def cmd_folders(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    if not path.exists():
        log.error("no roster for %s", args.classname)
        return 1
    inbox = discover_inbox()
    inbox.mkdir(parents=True, exist_ok=True)
    _header, rows = read_roster(path)

    if args.clean:
        # Remove existing per-student folders for this class only
        for entry in inbox.iterdir():
            if entry.is_dir() and entry.name.startswith(f"{args.classname}-"):
                if any(entry.iterdir()):
                    log.warning("skip non-empty %s", entry.name)
                    continue
                entry.rmdir()
                log.info("removed empty %s", entry.name)

    created = 0
    for row in rows:
        name = row["name"].strip()
        folder_name = (
            f"{args.classname}-{slugify(name)}" if args.prefix else slugify(name)
        )
        target = inbox / folder_name
        if target.exists():
            continue
        target.mkdir()
        created += 1
    log.info("created %d folder(s) in %s", created, inbox)
    return 0


# ---------------------------------------------------------------------------
# PDF generation (sheet / nametags)
# ---------------------------------------------------------------------------

def _import_reportlab():
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        return canvas, letter
    except ImportError as exc:
        raise RuntimeError(
            "reportlab not installed — `python -m pip install --user reportlab`"
        ) from exc


def render_sheet(class_name: str, names: list[str], output: Path) -> None:
    canvas_mod, letter = _import_reportlab()
    output.parent.mkdir(parents=True, exist_ok=True)
    page_w, page_h = letter
    c = canvas_mod.Canvas(str(output), pagesize=letter)

    margin_x = 54
    margin_y = 54
    title = class_name
    c.setFont("Helvetica-Bold", 22)
    c.drawString(margin_x, page_h - margin_y, title)
    c.setFont("Helvetica", 10)
    c.setFillGray(0.4)
    sub = f"{len(names)} scholars · generated {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    c.drawString(margin_x, page_h - margin_y - 18, sub)
    c.setFillGray(0)

    y = page_h - margin_y - 56
    line_height = 22
    columns = 2 if len(names) > 24 else 1
    if columns == 2:
        column_width = (page_w - margin_x * 2) / 2
        per_column = math.ceil(len(names) / 2)
        for col in range(2):
            cy = y
            base = col * per_column
            for i in range(per_column):
                idx = base + i
                if idx >= len(names):
                    break
                cx = margin_x + col * column_width
                c.setFont("Helvetica", 11)
                c.setFillGray(0.55)
                c.drawString(cx, cy, f"{idx + 1:2d}.")
                c.setFillGray(0)
                c.setFont("Helvetica", 12)
                c.drawString(cx + 24, cy, names[idx])
                # signature line
                c.setStrokeGray(0.7)
                c.line(cx + column_width - 110, cy - 4,
                       cx + column_width - 12, cy - 4)
                cy -= line_height
                if cy < margin_y + 30:
                    c.showPage()
                    cy = page_h - margin_y
    else:
        for i, name in enumerate(names):
            c.setFont("Helvetica", 11)
            c.setFillGray(0.55)
            c.drawString(margin_x, y, f"{i + 1:2d}.")
            c.setFillGray(0)
            c.setFont("Helvetica", 13)
            c.drawString(margin_x + 28, y, name)
            c.setStrokeGray(0.7)
            c.line(margin_x + 220, y - 4, page_w - margin_x, y - 4)
            y -= line_height
            if y < margin_y + 30:
                c.showPage()
                y = page_h - margin_y
    c.showPage()
    c.save()


def render_nametags(class_name: str, names: list[str], output: Path,
                    per_page: int = 6) -> None:
    canvas_mod, letter = _import_reportlab()
    output.parent.mkdir(parents=True, exist_ok=True)
    page_w, page_h = letter
    c = canvas_mod.Canvas(str(output), pagesize=letter)

    cols = 2 if per_page <= 8 else 3
    rows = math.ceil(per_page / cols)
    margin = 36
    cell_w = (page_w - margin * 2) / cols
    cell_h = (page_h - margin * 2) / rows
    inner_pad = 12

    for index, name in enumerate(names):
        slot = index % per_page
        row = slot // cols
        col = slot % cols
        x = margin + col * cell_w
        y = page_h - margin - (row + 1) * cell_h
        c.setStrokeGray(0.65)
        c.setLineWidth(0.6)
        c.roundRect(x + 4, y + 4, cell_w - 8, cell_h - 8, 12, stroke=1, fill=0)
        c.setFillGray(0.4)
        c.setFont("Helvetica", 9)
        c.drawString(x + inner_pad, y + cell_h - inner_pad - 8, class_name.upper())
        c.setFillGray(0)
        # Auto-shrink font to fit
        font_size = 36
        max_width = cell_w - 2 * inner_pad
        while font_size > 14:
            c.setFont("Helvetica-Bold", font_size)
            if c.stringWidth(name, "Helvetica-Bold", font_size) <= max_width:
                break
            font_size -= 2
        c.setFont("Helvetica-Bold", font_size)
        text_y = y + cell_h / 2 - font_size / 3
        c.drawString(x + inner_pad, text_y, name)

        if slot == per_page - 1 and index < len(names) - 1:
            c.showPage()
    c.showPage()
    c.save()


def cmd_sheet(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    if not path.exists():
        log.error("no roster for %s", args.classname)
        return 1
    _, rows = read_roster(path)
    names = names_only(rows)
    output = _resolve_pdf_output(args, default_name=f"{slugify(args.classname)}-roster.pdf")
    render_sheet(args.classname, names, output)
    log.info("wrote %s (%d scholars)", output, len(names))
    return 0


def cmd_nametags(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    if not path.exists():
        log.error("no roster for %s", args.classname)
        return 1
    _, rows = read_roster(path)
    names = names_only(rows)
    output = _resolve_pdf_output(
        args, default_name=f"{slugify(args.classname)}-nametags.pdf",
    )
    render_nametags(args.classname, names, output, per_page=args.per_page)
    log.info("wrote %s (%d scholars across %d-up tags)",
             output, len(names), args.per_page)
    return 0


def _resolve_pdf_output(args: argparse.Namespace, default_name: str) -> Path:
    if args.to_inbox:
        return discover_inbox() / default_name
    if args.out is not None:
        return args.out
    return Path.cwd() / default_name


# ---------------------------------------------------------------------------
# Groups, split, stamp
# ---------------------------------------------------------------------------

def cmd_groups(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    if not path.exists():
        log.error("no roster for %s", args.classname)
        return 1
    _, rows = read_roster(path)
    names = names_only(rows)
    if args.size < 2:
        log.error("--size must be >= 2")
        return 2
    rng = random.Random(args.seed)
    shuffled = list(names)
    rng.shuffle(shuffled)
    groups: list[list[str]] = []
    for i in range(0, len(shuffled), args.size):
        groups.append(shuffled[i:i + args.size])
    log.info("%s — %d group(s) of up to %d (seed=%s):",
             args.classname, len(groups), args.size, args.seed)
    for i, group in enumerate(groups, 1):
        log.info("  Group %d: %s", i, ", ".join(group))
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    path = class_path(args.classname)
    if not path.exists():
        log.error("no roster for %s", args.classname)
        return 1
    if not args.pdf.exists():
        log.error("PDF not found: %s", args.pdf)
        return 1
    sibling = Path(__file__).resolve().parent / "roster_split.py"
    if not sibling.exists():
        log.error("roster_split.py not next to roster.py")
        return 2
    cmd = [sys.executable, str(sibling), "--pdf", str(args.pdf),
           "--roster", str(path)]
    if args.pages_per_student:
        cmd += ["--pages-per-student", str(args.pages_per_student)]
    if args.to_inbox:
        cmd.append("--to-inbox")
    elif args.out:
        cmd += ["--out", str(args.out)]
    log.info("running: %s", " ".join(cmd))
    return subprocess.call(cmd)


def cmd_stamp(args: argparse.Namespace) -> int:
    """Generate per-scholar copies of a worksheet, each stamped with the name."""
    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
    except ImportError:
        log.error("install pypdf + reportlab: `python -m pip install --user pypdf reportlab`")
        return 2
    import io
    path = class_path(args.classname)
    if not path.exists():
        log.error("no roster for %s", args.classname)
        return 1
    if not args.pdf.exists():
        log.error("PDF not found: %s", args.pdf)
        return 1
    _, rows = read_roster(path)
    names = names_only(rows)
    if not names:
        log.error("roster is empty")
        return 1
    output_dir = (
        discover_inbox() if args.to_inbox
        else (args.out or args.pdf.parent / f"{args.pdf.stem}-stamped")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    for name in names:
        reader = PdfReader(str(args.pdf))
        writer = PdfWriter()
        for page in reader.pages:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(width, height))
            c.setFont("Helvetica-Bold", 11)
            c.setFillColorRGB(0.15, 0.15, 0.15)
            margin = 18
            stamp = f"{name} · {today} · {args.classname}"
            c.drawRightString(width - margin, height - margin - 4, stamp)
            c.showPage()
            c.save()
            overlay = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
            page.merge_page(overlay)
            writer.add_page(page)
        target = output_dir / f"{slugify(name)}-{args.pdf.stem}.pdf"
        with target.open("wb") as fh:
            writer.write(fh)
        log.info("wrote %s", target.name)
    log.info("done: %d scholar(s)", len(names))
    return 0


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("classes", help="list all rosters").set_defaults(func=cmd_classes)

    p = sub.add_parser("init", help="create a new empty roster")
    p.add_argument("classname")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("add", help="add a scholar to a roster")
    p.add_argument("classname")
    p.add_argument("name")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("remove", help="remove a scholar")
    p.add_argument("classname")
    p.add_argument("name")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("rename", help="rename a scholar")
    p.add_argument("classname")
    p.add_argument("old")
    p.add_argument("new")
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("list", help="show a roster")
    p.add_argument("classname")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("import", help="import names from a text file (one per line)")
    p.add_argument("classname")
    p.add_argument("file", type=Path)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("export", help="copy the roster CSV elsewhere")
    p.add_argument("classname")
    p.add_argument("--out", type=Path, default=None)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("folders", help="create per-scholar folders in PrintInbox")
    p.add_argument("classname")
    p.add_argument("--prefix", action="store_true",
                   help="prefix folder names with the class name (avoids collisions)")
    p.add_argument("--clean", action="store_true",
                   help="remove empty class-prefixed folders first")
    p.set_defaults(func=cmd_folders)

    p = sub.add_parser("sheet", help="generate a printable class roster PDF")
    p.add_argument("classname")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--to-inbox", action="store_true")
    p.set_defaults(func=cmd_sheet)

    p = sub.add_parser("nametags", help="generate a printable name-tag grid PDF")
    p.add_argument("classname")
    p.add_argument("--per-page", type=int, default=6, choices=(2, 4, 6, 8, 9, 12))
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--to-inbox", action="store_true")
    p.set_defaults(func=cmd_nametags)

    p = sub.add_parser("groups", help="random group assignments")
    p.add_argument("classname")
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--seed", type=int, default=None)
    p.set_defaults(func=cmd_groups)

    p = sub.add_parser("split", help="split a packet PDF using the roster (wraps roster_split.py)")
    p.add_argument("classname")
    p.add_argument("pdf", type=Path)
    p.add_argument("--pages-per-student", type=int, default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--to-inbox", action="store_true")
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("stamp", help="per-scholar stamped copies of a worksheet")
    p.add_argument("classname")
    p.add_argument("pdf", type=Path)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--to-inbox", action="store_true")
    p.set_defaults(func=cmd_stamp)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
