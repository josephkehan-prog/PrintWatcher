"""Pre-create iPad-friendly preset folders inside PrintInbox.

Once these folders exist in OneDrive, your iPad just shares the PDF
straight into one of them — no filename editing needed. The folder name's
`__opts` suffix is parsed by the watcher exactly like the filename suffix.

Default preset set:

    __copies=30          (30 copies, otherwise UI defaults)
    __copies=15          (15 copies)
    __duplex             (duplex long-edge)
    __mono               (monochrome)
    __duplex_mono        (duplex + monochrome — common "draft" combo)
    __copies=30_duplex   (full class set)

Run:
    python scripts/setup_inbox_presets.py            # creates the defaults
    python scripts/setup_inbox_presets.py --list     # lists what's already there
    python scripts/setup_inbox_presets.py __color    # add custom presets

Submitter folders (e.g. PrintInbox/MaryDoe) are out of scope — make those
yourself, or pass them in: `setup_inbox_presets.py MaryDoe Class3__copies=30`.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

DEFAULT_PRESETS = (
    "__copies=30",
    "__copies=15",
    "__duplex",
    "__mono",
    "__duplex_mono",
    "__copies=30_duplex",
)

log = logging.getLogger("printwatcher.presets")


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


def list_presets(inbox: Path) -> list[str]:
    if not inbox.exists():
        return []
    return sorted(
        entry.name for entry in inbox.iterdir()
        if entry.is_dir() and entry.name != "_printed" and "__" in entry.name
    )


def create_presets(inbox: Path, names: list[str]) -> tuple[list[str], list[str]]:
    inbox.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    existed: list[str] = []
    for name in names:
        target = inbox / name
        if target.exists():
            existed.append(name)
            continue
        target.mkdir()
        created.append(name)
    return created, existed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "presets", nargs="*",
        help="preset folder names (default: a curated starter set)",
    )
    parser.add_argument("--list", action="store_true",
                        help="list preset folders that already exist and exit")
    parser.add_argument("--inbox", type=Path, default=None,
                        help="override PrintInbox path (defaults to auto-discovery)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    inbox = args.inbox or discover_inbox()
    log.info("inbox: %s", inbox)

    if args.list:
        names = list_presets(inbox)
        if names:
            log.info("existing preset folders (%d):", len(names))
            for n in names:
                log.info("  %s", n)
        else:
            log.info("no preset folders found")
        return 0

    names = args.presets or list(DEFAULT_PRESETS)
    created, existed = create_presets(inbox, names)
    if created:
        log.info("created (%d):", len(created))
        for n in created:
            log.info("  %s", n)
    if existed:
        log.info("already existed (%d):", len(existed))
        for n in existed:
            log.info("  %s", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
