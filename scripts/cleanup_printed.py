"""Sweep old files out of `<inbox>/_printed/` so OneDrive doesn't bloat.

By default, files older than `--days` (30) are *moved* into a dated
archive folder (`_printed/_archive/YYYY-MM/`) so you keep them but they
no longer clutter the live tree. Use `--delete` to actually remove them.

Always dry-run unless `--apply` is passed.

Usage:
    python scripts/cleanup_printed.py                    # dry-run (default)
    python scripts/cleanup_printed.py --apply            # archive >30d
    python scripts/cleanup_printed.py --apply --days 14  # tighter window
    python scripts/cleanup_printed.py --apply --delete   # rm instead of archive
    python scripts/cleanup_printed.py --apply --gzip     # tar.gz the month folder

Wire it to weekly Task Scheduler:
    powershell> schtasks /Create /TN "PrintWatcherCleanup" /SC WEEKLY /D SUN ^
        /ST 03:00 /TR "python C:\\path\\to\\scripts\\cleanup_printed.py --apply"

Stdlib only.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
import tarfile
import time
from datetime import datetime, timedelta
from pathlib import Path

PRINTED_SUBDIR = "_printed"
ARCHIVE_SUBDIR = "_archive"
DEFAULT_DAYS = 30

log = logging.getLogger("printwatcher.cleanup")


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


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def collect_old_files(printed_dir: Path, cutoff_age_days: int) -> list[Path]:
    if not printed_dir.exists():
        return []
    cutoff = time.time() - (cutoff_age_days * 86400)
    archive_root = printed_dir / ARCHIVE_SUBDIR
    found: list[Path] = []
    for entry in printed_dir.rglob("*"):
        if not entry.is_file():
            continue
        if archive_root in entry.parents:
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if mtime <= cutoff:
            found.append(entry)
    return found


def archive_files(files: list[Path], printed_dir: Path,
                  use_gzip: bool) -> tuple[int, int]:
    """Move each file into `_archive/<YYYY-MM>/<original-relative-path>`.

    If `use_gzip` is True, after moving each month's files we wrap that
    month folder in a `.tar.gz` and remove the source dir.
    """
    archive_root = printed_dir / ARCHIVE_SUBDIR
    moved = 0
    bytes_moved = 0
    months_touched: set[Path] = set()
    for path in files:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            mtime = datetime.now()
        month_dir = archive_root / mtime.strftime("%Y-%m")
        try:
            relative = path.relative_to(printed_dir)
        except ValueError:
            relative = Path(path.name)
        target = month_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target = target.with_name(
                f"{target.stem}-{int(time.time())}{target.suffix}"
            )
        try:
            size = path.stat().st_size
            shutil.move(str(path), str(target))
            moved += 1
            bytes_moved += size
            months_touched.add(month_dir)
        except OSError as exc:
            log.warning("could not archive %s: %s", path.name, exc)

    if use_gzip:
        for month_dir in months_touched:
            tar_path = month_dir.with_suffix(".tar.gz")
            try:
                with tarfile.open(tar_path, "w:gz") as tf:
                    tf.add(month_dir, arcname=month_dir.name)
                shutil.rmtree(month_dir)
                log.info("compressed %s -> %s", month_dir.name, tar_path.name)
            except OSError as exc:
                log.warning("could not gzip %s: %s", month_dir, exc)

    return moved, bytes_moved


def delete_files(files: list[Path]) -> tuple[int, int]:
    deleted = 0
    bytes_deleted = 0
    for path in files:
        try:
            size = path.stat().st_size
            path.unlink()
            deleted += 1
            bytes_deleted += size
        except OSError as exc:
            log.warning("could not delete %s: %s", path.name, exc)
    return deleted, bytes_deleted


def remove_empty_dirs(printed_dir: Path) -> int:
    removed = 0
    for entry in sorted(printed_dir.rglob("*"), reverse=True):
        if not entry.is_dir():
            continue
        if entry == printed_dir / ARCHIVE_SUBDIR:
            continue
        try:
            entry.rmdir()
            removed += 1
        except OSError:
            pass  # not empty, fine
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--inbox", type=Path, default=None,
                        help="override PrintInbox path")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help=f"sweep files older than this many days (default {DEFAULT_DAYS})")
    parser.add_argument("--apply", action="store_true",
                        help="actually move/delete (default: dry-run preview)")
    parser.add_argument("--delete", action="store_true",
                        help="delete instead of archiving")
    parser.add_argument("--gzip", action="store_true",
                        help="compress each month's archive into a .tar.gz")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    inbox = args.inbox or discover_inbox()
    printed_dir = inbox / PRINTED_SUBDIR
    log.info("inbox  : %s", inbox)
    log.info("printed: %s", printed_dir)
    log.info("cutoff : %s (older than %d day(s))",
             (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d"),
             args.days)

    files = collect_old_files(printed_dir, args.days)
    if not files:
        log.info("nothing to do — no files older than %d day(s)", args.days)
        return 0

    total_bytes = sum(p.stat().st_size for p in files if p.exists())
    log.info("found %d file(s), total %s",
             len(files), _format_size(total_bytes))

    if not args.apply:
        log.info("dry-run — re-run with --apply to %s",
                 "delete" if args.delete else "archive")
        # Show a preview of the first 10
        for path in files[:10]:
            try:
                relative = path.relative_to(printed_dir)
            except ValueError:
                relative = path
            log.info("  %s", relative)
        if len(files) > 10:
            log.info("  ... and %d more", len(files) - 10)
        return 0

    if args.delete:
        deleted, bytes_deleted = delete_files(files)
        log.info("deleted %d file(s), reclaimed %s",
                 deleted, _format_size(bytes_deleted))
    else:
        moved, bytes_moved = archive_files(files, printed_dir, args.gzip)
        log.info("archived %d file(s) (%s) into %s/",
                 moved, _format_size(bytes_moved), ARCHIVE_SUBDIR)

    removed_dirs = remove_empty_dirs(printed_dir)
    if removed_dirs:
        log.info("removed %d empty subfolder(s)", removed_dirs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
