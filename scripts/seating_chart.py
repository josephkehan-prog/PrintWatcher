"""Generate a seating chart PDF from a class roster.

Two arrangement modes:

    --random       shuffle scholars into a grid (default)
    --alphabetical place by last name then first

Pair / group constraints:

    --pair "Mary Doe + John Smith"     keep these two adjacent
    --separate "Alex Wong / Sam Park"   never seat these two adjacent

The chart is rendered as an N×M grid of name cards (default 5×6 = 30
seats). Empty seats become small dashed rectangles.

Usage:
    python scripts/seating_chart.py --class Hamilton
    python scripts/seating_chart.py --class Hamilton --rows 4 --cols 7 --to-inbox
    python scripts/seating_chart.py --class Hamilton --alphabetical \\
        --pair "Mary Doe + John Smith"
    python scripts/seating_chart.py --class Hamilton --random --seed 42

Dependencies:
    python -m pip install --user reportlab
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import random
import re
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger("printwatcher.seating")


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
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = (row.get("name") or "").strip()
            if name:
                rows.append(row)
    return rows


def parse_pair(spec: str) -> tuple[str, str]:
    for sep in ("+", "&", "/"):
        if sep in spec:
            left, right = spec.split(sep, 1)
            return left.strip(), right.strip()
    raise ValueError(f"could not parse pair {spec!r} (use 'A + B', 'A & B', or 'A / B')")


def _adjacent_indices(idx: int, rows: int, cols: int) -> set[int]:
    r, c = divmod(idx, cols)
    out: set[int] = set()
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                out.add(nr * cols + nc)
    return out


def assign_seats(
    names: list[str],
    rows: int,
    cols: int,
    arrangement: str,
    pairs: list[tuple[str, str]],
    separates: list[tuple[str, str]],
    rng: random.Random,
) -> list[str | None]:
    """Returns a flat list of `rows * cols` seats. None means empty seat."""
    capacity = rows * cols
    if len(names) > capacity:
        log.warning("only %d seats; %d scholar(s) won't fit", capacity, len(names))
        names = names[:capacity]

    if arrangement == "alphabetical":
        ordered = sorted(names, key=lambda n: (n.split()[-1].lower(), n.lower()))
    else:
        ordered = list(names)
        rng.shuffle(ordered)

    seats: list[str | None] = list(ordered) + [None] * (capacity - len(ordered))

    # Apply pairing constraints (best-effort, swap-based)
    by_name = {name.lower(): idx for idx, name in enumerate(seats) if name}
    for a, b in pairs:
        i = by_name.get(a.lower())
        j = by_name.get(b.lower())
        if i is None or j is None:
            log.warning("pair (%s, %s): one or both not on the roster", a, b)
            continue
        if j in _adjacent_indices(i, rows, cols):
            continue
        # Find an adjacent slot to i that is either empty or holds someone
        # not in any constraint, and swap.
        for k in _adjacent_indices(i, rows, cols):
            if k == j:
                continue
            seats[j], seats[k] = seats[k], seats[j]
            by_name = {name.lower(): idx for idx, name in enumerate(seats) if name}
            break

    # Honour --separate by swapping one of the two with a random non-adjacent seat
    for attempts in range(len(separates) * 4 + 1):
        violation = None
        for a, b in separates:
            i = by_name.get(a.lower())
            j = by_name.get(b.lower())
            if i is None or j is None:
                continue
            if j in _adjacent_indices(i, rows, cols):
                violation = (i, j)
                break
        if not violation:
            break
        i, j = violation
        candidates = [
            k for k in range(capacity)
            if k != i and k != j and k not in _adjacent_indices(i, rows, cols)
        ]
        if not candidates:
            log.warning("could not separate %s and %s — no eligible swap",
                        seats[i], seats[j])
            break
        target = rng.choice(candidates)
        seats[j], seats[target] = seats[target], seats[j]
        by_name = {name.lower(): idx for idx, name in enumerate(seats) if name}

    return seats


def render(
    class_name: str,
    seats: list[str | None],
    rows: int,
    cols: int,
    output: Path,
    target_date: date,
    front_label: str,
) -> None:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.pdfgen import canvas

    output.parent.mkdir(parents=True, exist_ok=True)
    page_w, page_h = landscape(letter)
    c = canvas.Canvas(str(output), pagesize=landscape(letter))

    margin = 36
    title_h = 60
    grid_top = page_h - margin - title_h
    grid_bottom = margin + 30
    grid_left = margin
    grid_right = page_w - margin
    cell_w = (grid_right - grid_left) / cols
    cell_h = (grid_top - grid_bottom) / rows

    c.setFont("Helvetica-Bold", 22)
    c.drawString(margin, page_h - margin - 4, f"{class_name} — seating chart")
    c.setFont("Helvetica", 11)
    c.setFillGray(0.45)
    c.drawString(margin, page_h - margin - 22,
                 f"{target_date.strftime('%A, %B %d, %Y')} · {rows}×{cols} = {rows*cols} seats")
    c.setFillGray(0)

    # Front-of-room label
    c.setFont("Helvetica-Bold", 10)
    c.setFillGray(0.4)
    c.drawCentredString(page_w / 2, grid_top + 8, front_label.upper())
    c.setFillGray(0)

    pad = 6
    for index, name in enumerate(seats):
        r, ccol = divmod(index, cols)
        x = grid_left + ccol * cell_w
        y = grid_top - (r + 1) * cell_h
        if name is None:
            c.setStrokeGray(0.75)
            c.setDash(4, 4)
            c.rect(x + pad, y + pad, cell_w - 2 * pad, cell_h - 2 * pad, stroke=1, fill=0)
            c.setDash()  # clear dash
            continue
        c.setStrokeGray(0.55)
        c.setLineWidth(0.6)
        c.roundRect(x + pad, y + pad, cell_w - 2 * pad, cell_h - 2 * pad, 8, stroke=1, fill=0)
        # Auto-fit name
        size = 18
        max_width = cell_w - 2 * pad - 12
        while size > 10:
            c.setFont("Helvetica-Bold", size)
            if c.stringWidth(name, "Helvetica-Bold", size) <= max_width:
                break
            size -= 1
        c.setFont("Helvetica-Bold", size)
        c.drawCentredString(x + cell_w / 2, y + cell_h / 2 - size / 3, name)

    # Footer
    c.setFillGray(0.55)
    c.setFont("Helvetica", 7)
    c.drawString(margin, margin / 2,
                 f"PrintWatcher · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.showPage()
    c.save()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--class", dest="classname", required=True)
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument("--cols", type=int, default=6)
    arrangement = parser.add_mutually_exclusive_group()
    arrangement.add_argument("--random", action="store_const",
                             dest="arrangement", const="random")
    arrangement.add_argument("--alphabetical", action="store_const",
                             dest="arrangement", const="alphabetical")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--pair", action="append", default=[],
                        help="keep two scholars adjacent (e.g. 'A + B'); repeatable")
    parser.add_argument("--separate", action="append", default=[],
                        help="never seat two scholars adjacent; repeatable")
    parser.add_argument("--front-label", default="front of room")
    parser.add_argument("--date", default=None,
                        help="YYYY-MM-DD (default: today)")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--to-inbox", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    target_date = date.fromisoformat(args.date) if args.date else date.today()

    try:
        roster = load_roster(args.classname, args.csv)
    except FileNotFoundError as exc:
        log.error("roster not found: %s", exc)
        return 1
    names = [row["name"].strip() for row in roster if row.get("name", "").strip()]
    if not names:
        log.error("roster is empty")
        return 1

    pairs = [parse_pair(spec) for spec in args.pair]
    separates = [parse_pair(spec) for spec in args.separate]

    rng = random.Random(args.seed)
    seats = assign_seats(
        names, args.rows, args.cols,
        arrangement=args.arrangement or "random",
        pairs=pairs, separates=separates,
        rng=rng,
    )

    if args.to_inbox:
        output = discover_inbox() / f"seating-{slugify(args.classname)}-{target_date.isoformat()}.pdf"
    else:
        output = args.out or Path.cwd() / f"seating-{slugify(args.classname)}-{target_date.isoformat()}.pdf"

    try:
        render(args.classname, seats, args.rows, args.cols, output,
               target_date, args.front_label)
    except ImportError:
        log.error("reportlab required: `python -m pip install --user reportlab`")
        return 2
    log.info("wrote %s (%d×%d, %d scholar(s))",
             output, args.rows, args.cols, len(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
