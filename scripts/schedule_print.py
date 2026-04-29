"""Hold a print job until a specific time, then release it into PrintInbox.

Two modes:

    # Schedule a one-shot — encodes time into the filename and runs the
    # daemon in the background. The watcher won't see the file until the
    # daemon moves it.
    python scripts/schedule_print.py worksheet.pdf --at "2026-04-30T08:00"
    python scripts/schedule_print.py worksheet.pdf --at "8am tomorrow"
    python scripts/schedule_print.py worksheet.pdf --in 2h
    python scripts/schedule_print.py worksheet.pdf --in 30m

    # Daemon — keep this running (or wire it into Startup folder) to
    # honour scheduled files. Polls every 30 s.
    python scripts/schedule_print.py --daemon

    # List what's scheduled
    python scripts/schedule_print.py --list
    python scripts/schedule_print.py --cancel <filename>

Held files live in `<inbox>/_scheduled/`. Each is renamed to
    YYYY-MM-DDTHH-MM__<original-name>
so the time is human-readable in OneDrive too. When the daemon sees a
prefix whose time has passed, it strips the prefix and moves the file
into the inbox root (where the main watcher picks it up immediately).

Stdlib only.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

POLL_INTERVAL_SEC = 30.0
SCHEDULED_SUBDIR = "_scheduled"
TIME_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}-\d{2})__(.+)$")

log = logging.getLogger("printwatcher.schedule")


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


def parse_time(spec: str, now: datetime | None = None) -> datetime:
    """Accepts ISO 8601 ('2026-04-30T08:00'), '8am tomorrow', '8:30am', '14:00'."""
    now = now or datetime.now()
    spec = spec.strip()
    # ISO first
    try:
        return datetime.fromisoformat(spec)
    except ValueError:
        pass

    lowered = spec.lower()
    tomorrow = "tomorrow" in lowered
    today = "today" in lowered or not tomorrow
    lowered = lowered.replace("tomorrow", "").replace("today", "").strip()

    # 8am, 8:30am, 14:00
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", lowered)
    if not match:
        raise ValueError(f"could not parse time: {spec!r}")
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    base_date = now.date()
    if tomorrow:
        base_date += timedelta(days=1)
    target = datetime.combine(base_date, datetime.min.time()).replace(hour=hour, minute=minute)
    if today and target <= now:
        target += timedelta(days=1)
    return target


def parse_offset(spec: str) -> timedelta:
    spec = spec.strip().lower()
    match = re.fullmatch(r"(\d+)\s*(s|m|h|d)", spec)
    if not match:
        raise ValueError(f"could not parse offset: {spec!r}")
    n = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return timedelta(seconds=n)
    if unit == "m":
        return timedelta(minutes=n)
    if unit == "h":
        return timedelta(hours=n)
    return timedelta(days=n)


def schedule_one(source: Path, when: datetime, scheduled_dir: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(source)
    scheduled_dir.mkdir(parents=True, exist_ok=True)
    prefix = when.strftime("%Y-%m-%dT%H-%M")
    target = scheduled_dir / f"{prefix}__{source.name}"
    while target.exists():
        target = target.with_name(f"{target.stem}-{int(time.time())}{target.suffix}")
    shutil.move(str(source), str(target))
    return target


def list_scheduled(scheduled_dir: Path) -> list[tuple[datetime, Path]]:
    if not scheduled_dir.exists():
        return []
    out: list[tuple[datetime, Path]] = []
    for entry in scheduled_dir.iterdir():
        if not entry.is_file():
            continue
        match = TIME_PREFIX.match(entry.name)
        if not match:
            continue
        try:
            when = datetime.strptime(match.group(1), "%Y-%m-%dT%H-%M")
        except ValueError:
            continue
        out.append((when, entry))
    return sorted(out, key=lambda pair: pair[0])


def cancel(scheduled_dir: Path, filename_substring: str) -> int:
    cancelled = 0
    for _when, path in list_scheduled(scheduled_dir):
        if filename_substring.lower() in path.name.lower():
            try:
                path.unlink()
                cancelled += 1
                log.info("cancelled %s", path.name)
            except OSError as exc:
                log.warning("could not cancel %s: %s", path.name, exc)
    return cancelled


def daemon(inbox: Path, scheduled_dir: Path) -> None:
    log.info("daemon watching %s; releasing into %s", scheduled_dir, inbox)
    while True:
        try:
            now = datetime.now()
            for when, path in list_scheduled(scheduled_dir):
                if when > now:
                    continue
                match = TIME_PREFIX.match(path.name)
                if not match:
                    continue
                target = inbox / match.group(2)
                while target.exists():
                    target = target.with_name(f"{target.stem}-{int(time.time())}{target.suffix}")
                try:
                    shutil.move(str(path), str(target))
                    log.info("released %s -> %s", path.name, target.name)
                except OSError as exc:
                    log.warning("could not release %s: %s", path.name, exc)
        except OSError as exc:
            log.warning("scheduled scan failed: %s", exc)
        time.sleep(POLL_INTERVAL_SEC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", nargs="?", type=Path, help="file to schedule")
    parser.add_argument("--at", help="absolute time (ISO 8601 or '8am tomorrow')")
    parser.add_argument("--in", dest="offset",
                        help="relative offset like 30m, 2h, 1d")
    parser.add_argument("--daemon", action="store_true", help="run the release daemon")
    parser.add_argument("--list", action="store_true", help="list scheduled files")
    parser.add_argument("--cancel", help="cancel scheduled files matching this filename substring")
    parser.add_argument("--inbox", type=Path, default=None,
                        help="override PrintInbox path")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    inbox = args.inbox or discover_inbox()
    scheduled_dir = inbox / SCHEDULED_SUBDIR

    if args.daemon:
        try:
            daemon(inbox, scheduled_dir)
        except KeyboardInterrupt:
            log.info("daemon stopped")
        return 0

    if args.list:
        items = list_scheduled(scheduled_dir)
        if not items:
            log.info("nothing scheduled in %s", scheduled_dir)
            return 0
        log.info("scheduled (%d):", len(items))
        for when, path in items:
            match = TIME_PREFIX.match(path.name)
            display_name = match.group(2) if match else path.name
            log.info("  %s   %s", when.strftime("%Y-%m-%d %H:%M"), display_name)
        return 0

    if args.cancel:
        count = cancel(scheduled_dir, args.cancel)
        log.info("cancelled %d file(s)", count)
        return 0 if count else 1

    if args.input is None:
        parser.error("input file required (or --daemon / --list / --cancel)")

    if args.at and args.offset:
        parser.error("--at and --in are mutually exclusive")
    try:
        if args.offset:
            when = datetime.now() + parse_offset(args.offset)
        elif args.at:
            when = parse_time(args.at)
        else:
            parser.error("--at or --in is required when scheduling a file")
    except ValueError as exc:
        parser.error(str(exc))

    if when <= datetime.now():
        parser.error("scheduled time is in the past")

    target = schedule_one(args.input, when, scheduled_dir)
    log.info("scheduled %s -> %s", args.input.name, target.relative_to(inbox))
    log.info("releases at %s (run --daemon to honour it)",
             when.strftime("%Y-%m-%d %H:%M"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
