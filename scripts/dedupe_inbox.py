"""Detect duplicate files in PrintInbox by content hash, before they reprint.

The iPad share sheet sometimes saves a file twice on a flaky connection,
or a teacher drops the same packet for multiple submitters. This script
sweeps the inbox, hashes every candidate file, and moves duplicates into
`_skipped/` so the watcher ignores them.

Usage:
    python scripts/dedupe_inbox.py                 # dry-run report
    python scripts/dedupe_inbox.py --apply         # move dupes to _skipped/
    python scripts/dedupe_inbox.py --apply --include-printed
                                                   # also compare against
                                                   #   files already in _printed/

Within a single run, the **oldest** file (earliest mtime) keeps its place;
younger files with the same hash are moved.

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

EXTS = frozenset({".pdf", ".png", ".jpg", ".jpeg"})
PRINTED_SUBDIR = "_printed"
SKIPPED_SUBDIR = "_skipped"
HASH_CHUNK = 1024 * 64

log = logging.getLogger("printwatcher.dedupe")


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


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_candidates(inbox: Path, include_printed: bool) -> list[Path]:
    if not inbox.exists():
        return []
    skipped_dir = inbox / SKIPPED_SUBDIR
    printed_dir = inbox / PRINTED_SUBDIR
    out: list[Path] = []
    for entry in inbox.rglob("*"):
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in EXTS:
            continue
        if skipped_dir in entry.parents or entry.parent == skipped_dir:
            continue
        if not include_printed and (printed_dir in entry.parents or entry.parent == printed_dir):
            continue
        out.append(entry)
    return out


def find_dupes(files: list[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        try:
            digest = hash_file(path)
        except OSError as exc:
            log.warning("could not hash %s: %s", path, exc)
            continue
        groups[digest].append(path)
    return {h: ps for h, ps in groups.items() if len(ps) > 1}


def _sort_key(path: Path) -> tuple[float, str]:
    try:
        return (path.stat().st_mtime, str(path))
    except OSError:
        return (0.0, str(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--inbox", type=Path, default=None,
                        help="override PrintInbox path")
    parser.add_argument("--apply", action="store_true",
                        help="actually move duplicates (default: dry run)")
    parser.add_argument("--include-printed", action="store_true",
                        help="also dedupe against files already in _printed/")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    inbox = args.inbox or discover_inbox()
    log.info("inbox: %s", inbox)

    files = collect_candidates(inbox, args.include_printed)
    if not files:
        log.info("no candidate files in inbox")
        return 0

    dupes = find_dupes(files)
    if not dupes:
        log.info("scanned %d file(s) — no duplicates", len(files))
        return 0

    skipped_dir = inbox / SKIPPED_SUBDIR
    moved = 0
    log.info("scanned %d file(s); %d duplicate group(s):", len(files), len(dupes))
    for digest, paths in dupes.items():
        ordered = sorted(paths, key=_sort_key)
        keeper = ordered[0]
        log.info("  group %s...", digest[:12])
        log.info("    keep:  %s", keeper.relative_to(inbox))
        for victim in ordered[1:]:
            log.info("    dupe:  %s", victim.relative_to(inbox))
            if args.apply:
                skipped_dir.mkdir(parents=True, exist_ok=True)
                target = skipped_dir / victim.name
                if target.exists():
                    target = skipped_dir / f"{target.stem}-{digest[:8]}{target.suffix}"
                try:
                    victim.rename(target)
                    moved += 1
                except OSError as exc:
                    log.warning("could not move %s: %s", victim, exc)

    if not args.apply:
        log.info("\nDry-run — re-run with --apply to move duplicates to %s",
                 skipped_dir.relative_to(inbox))
    else:
        log.info("\nmoved %d duplicate(s) to %s",
                 moved, skipped_dir.relative_to(inbox))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
