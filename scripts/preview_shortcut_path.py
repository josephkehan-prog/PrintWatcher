"""Preview the OneDrive path an iPad Shortcut would generate.

When you build the Custom Print Shortcut on iPad, the trickiest bit is
making sure the final filename actually parses on the watcher side. This
script takes the same inputs (copies, sides, color, submitter, filename)
and prints both the path PrintWatcher expects and the options it will
apply — so you can compare against what your Shortcut actually saved.

Usage:
    python scripts/preview_shortcut_path.py --copies 30 --sides duplex \\
        --color mono --submitter MaryDoe --filename quiz.pdf

    # Bare filename: just inbox root with options suffix
    python scripts/preview_shortcut_path.py --copies 12 --filename quiz.pdf

Options that resolve to "default" (the watcher's UI fallback) are dropped
from the path so the filename stays short.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SIDES_TOKEN = {
    "default": None,
    "single": "single",
    "simplex": "single",
    "duplex": "duplex",
    "duplexlong": "duplex",
    "long": "duplex",
    "short": "short",
    "duplexshort": "short",
}

COLOR_TOKEN = {
    "default": None,
    "color": "color",
    "colour": "color",
    "mono": "mono",
    "monochrome": "mono",
    "bw": "mono",
}


def build_path(
    copies: int,
    sides: str,
    color: str,
    submitter: str | None,
    filename: str,
) -> str:
    parts: list[str] = []
    if copies and copies > 1:
        parts.append(f"copies={copies}")
    sides_tok = SIDES_TOKEN.get(sides.lower())
    if sides_tok:
        parts.append(sides_tok)
    color_tok = COLOR_TOKEN.get(color.lower())
    if color_tok:
        parts.append(color_tok)

    stem = Path(filename).stem
    suffix = Path(filename).suffix or ".pdf"
    if parts:
        encoded_name = f"{stem}__{'_'.join(parts)}{suffix}"
    else:
        encoded_name = f"{stem}{suffix}"

    components: list[str] = []
    if submitter and submitter.strip():
        components.append(submitter.strip())
    components.append(encoded_name)
    return "/".join(components)


def describe(copies: int, sides: str, color: str) -> list[str]:
    out: list[str] = []
    if copies and copies > 1:
        out.append(f"{copies} copies")
    sides_tok = SIDES_TOKEN.get(sides.lower())
    if sides_tok == "duplex":
        out.append("duplex (long edge)")
    elif sides_tok == "short":
        out.append("duplex (short edge)")
    elif sides_tok == "single":
        out.append("single-sided")
    color_tok = COLOR_TOKEN.get(color.lower())
    if color_tok == "color":
        out.append("color")
    elif color_tok == "mono":
        out.append("monochrome")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--copies", type=int, default=1)
    parser.add_argument("--sides", default="default",
                        choices=sorted(SIDES_TOKEN.keys()))
    parser.add_argument("--color", default="default",
                        choices=sorted(COLOR_TOKEN.keys()))
    parser.add_argument("--submitter", default="")
    parser.add_argument("--filename", required=True,
                        help="original filename, e.g. quiz.pdf")
    args = parser.parse_args(argv)

    if args.copies < 1 or args.copies > 99:
        parser.error("--copies must be between 1 and 99")

    relative = build_path(
        copies=args.copies,
        sides=args.sides,
        color=args.color,
        submitter=args.submitter or None,
        filename=args.filename,
    )
    options = describe(args.copies, args.sides, args.color)

    print("Save the file inside OneDrive/PrintInbox at:")
    print()
    print(f"    PrintInbox/{relative}")
    print()
    print("PrintWatcher will apply:")
    if options:
        for line in options:
            print(f"  - {line}")
    else:
        print("  - (UI defaults — no overrides encoded)")
    submitter_label = args.submitter.strip() if args.submitter and args.submitter.strip() else "current Windows user"
    print(f"  - submitter: {submitter_label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
