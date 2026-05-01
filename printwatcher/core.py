"""UI-agnostic watcher core.

Contains everything the Tk UI and the FastAPI backend need to drive PrintWatcher
without any GUI ties: data classes, the option-parser surface, the history
store, the printer worker, the filesystem watcher, and a ``WatcherCore``
facade that wires them together.

Cut from ``print_watcher_ui.py`` (lines ~55-833) so the legacy module imports
from here and the new headless server can import the same pieces.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

APP_VERSION = "0.3.0"

EXTS = frozenset({".pdf", ".png", ".jpg", ".jpeg"})
POLL_INTERVAL_SEC = 5.0
STABLE_CHECKS = 3
STABLE_INTERVAL_SEC = 1.0
LOG_LINE_LIMIT = 500
PRINTED_SUBDIR = "_printed"
SKIPPED_SUBDIR = "_skipped"
SCHEDULED_SUBDIR = "_scheduled"
RESERVED_TOP_LEVEL = frozenset({PRINTED_SUBDIR, SKIPPED_SUBDIR, SCHEDULED_SUBDIR})

DEFAULT_SUMATRA = Path(r"C:\Tools\SumatraPDF\SumatraPDF.exe")
DEFAULT_PRINTER_LABEL = "Windows default printer"

SIDES_CHOICES: tuple[tuple[str, str | None], ...] = (
    ("Printer default", None),
    ("Single-sided (simplex)", "simplex"),
    ("Duplex (long edge)", "duplex"),
    ("Duplex (short edge)", "duplexshort"),
)
COLOR_CHOICES: tuple[tuple[str, str | None], ...] = (
    ("Printer default", None),
    ("Color", "color"),
    ("Monochrome", "monochrome"),
)

FILENAME_OPTIONS_SEPARATOR = "__"
FILENAME_TOKEN_SPLIT = re.compile(r"[,_\s]+")

log = logging.getLogger("printwatcher.core")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PrintOptions:
    """Per-job print settings applied to every file the watcher prints next."""

    printer: str | None = None
    copies: int = 1
    sides: str | None = None
    color: str | None = None

    def to_sumatra_args(self, sumatra: Path, target: Path) -> list[str]:
        cmd: list[str] = [str(sumatra)]
        if self.printer:
            cmd += ["-print-to", self.printer]
        else:
            cmd += ["-print-to-default"]

        settings: list[str] = []
        if self.copies > 1:
            settings.append(f"{self.copies}x")
        if self.sides:
            settings.append(self.sides)
        if self.color:
            settings.append(self.color)
        if settings:
            cmd += ["-print-settings", ",".join(settings)]

        cmd += ["-silent", "-exit-on-print", str(target)]
        return cmd


@dataclass(frozen=True)
class PrintRecord:
    """One row of the print history."""

    timestamp: str
    filename: str
    status: str
    detail: str = ""
    printer: str = ""
    copies: int = 1
    sides: str = ""
    color: str = ""
    submitter: str = ""

    @property
    def time_short(self) -> str:
        try:
            return datetime.fromisoformat(self.timestamp).strftime("%m/%d %H:%M")
        except ValueError:
            return self.timestamp


# ---------------------------------------------------------------------------
# Path discovery + filesystem helpers
# ---------------------------------------------------------------------------

def default_history_path() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "PrintWatcher" / "history.json"
    return Path.home() / ".printwatcher" / "history.json"


def _logs_dir() -> Path:
    base = os.environ.get("APPDATA")
    return Path(base) / "PrintWatcher" / "logs" if base else Path.home() / ".printwatcher" / "logs"


def _read_path_constant(text: str, name: str) -> Path | None:
    match = re.search(rf'{name}\s*=\s*Path\(r"([^"]+)"\)', text)
    if not match:
        return None
    raw = match.group(1)
    if "YOUR_USERNAME" in raw:
        return None
    return Path(raw)


def discover_paths() -> tuple[Path, Path]:
    """Return ``(watch_dir, sumatra_exe)``, preferring a sibling tray script."""
    watch_dir: Path | None = None
    sumatra: Path | None = None

    sibling = Path(__file__).resolve().parents[1] / "print_watcher_tray.py"
    if sibling.exists():
        try:
            text = sibling.read_text(encoding="utf-8", errors="ignore")
            watch_dir = _read_path_constant(text, "WATCH_DIR")
            sumatra = _read_path_constant(text, "SUMATRA")
        except OSError:
            pass

    if watch_dir is None:
        env_inbox = os.environ.get("PRINTWATCHER_INBOX")
        if env_inbox:
            watch_dir = Path(env_inbox)

    if watch_dir is None:
        onedrive = (
            os.environ.get("OneDrive")
            or os.environ.get("OneDriveCommercial")
            or os.environ.get("OneDriveConsumer")
        )
        base = Path(onedrive) if onedrive else Path.home() / "OneDrive"
        watch_dir = base / "PrintInbox"

    if sumatra is None:
        sumatra = DEFAULT_SUMATRA

    return watch_dir, sumatra


def _local_user() -> str:
    return (
        os.environ.get("USERNAME")
        or os.environ.get("USER")
        or "local"
    )


# ---------------------------------------------------------------------------
# Option parsing (filename + folder overlays)
# ---------------------------------------------------------------------------

def _apply_option_tokens(opt_str: str, base: PrintOptions) -> tuple[PrintOptions, list[str]]:
    """Parse a ``copies=3_duplex_color``-style token list into an option overlay."""
    merged = base
    applied: list[str] = []
    for raw in FILENAME_TOKEN_SPLIT.split(opt_str.lower()):
        token = raw.strip()
        if not token:
            continue
        if "=" in token:
            key, _, value = token.partition("=")
            if key in ("copies", "n", "x"):
                try:
                    count = max(1, min(99, int(value)))
                except ValueError:
                    continue
                merged = replace(merged, copies=count)
                applied.append(f"copies={count}")
            continue
        if token in {"duplex", "duplexlong", "long"}:
            merged = replace(merged, sides="duplex")
            applied.append("duplex")
        elif token in {"duplexshort", "short"}:
            merged = replace(merged, sides="duplexshort")
            applied.append("duplex (short)")
        elif token in {"simplex", "single"}:
            merged = replace(merged, sides="simplex")
            applied.append("single-sided")
        elif token in {"color", "colour"}:
            merged = replace(merged, color="color")
            applied.append("color")
        elif token in {"mono", "monochrome", "bw"}:
            merged = replace(merged, color="monochrome")
            applied.append("mono")
    return merged, applied


def split_label(label: str) -> tuple[str, str]:
    """Split ``<name>__<options>`` into ``(name, opt_str)``. Either may be empty."""
    if FILENAME_OPTIONS_SEPARATOR not in label:
        return label, ""
    name_part, _, opt_str = label.rpartition(FILENAME_OPTIONS_SEPARATOR)
    return name_part, opt_str


def parse_filename_options(filename: str, base: PrintOptions) -> tuple[PrintOptions, list[str]]:
    """Overlay options encoded in the filename suffix ``__copies=3_duplex_color``."""
    stem = Path(filename).stem
    name_part, opt_str = split_label(stem)
    if not opt_str or not name_part:
        return base, []
    return _apply_option_tokens(opt_str, base)


def resolve_path_options(
    path: Path,
    watch_dir: Path,
    base: PrintOptions,
) -> tuple[PrintOptions, list[str], str]:
    """Walk every path component under ``watch_dir`` and accumulate option overlays.

    Returns ``(merged_options, applied_tokens, submitter)``. The first folder
    component's name (with any ``__opts`` suffix stripped) determines the
    submitter. Folder option overlays apply in path order; the filename
    overlay applies last and wins on conflicts.
    """
    try:
        relative = path.relative_to(watch_dir)
    except ValueError:
        return base, [], _local_user()
    parts = relative.parts
    if not parts:
        return base, [], _local_user()

    options = base
    applied: list[str] = []
    submitter = _local_user()

    for index, part in enumerate(parts[:-1]):
        name_part, opt_str = split_label(part)
        if index == 0 and name_part:
            submitter = name_part
        if opt_str:
            options, tokens = _apply_option_tokens(opt_str, options)
            applied.extend(tokens)

    filename_stem = Path(parts[-1]).stem
    name_part, opt_str = split_label(filename_stem)
    if opt_str and name_part:
        options, tokens = _apply_option_tokens(opt_str, options)
        applied.extend(tokens)

    return options, applied, submitter


def _submitter_for(path: Path, watch_dir: Path) -> str:
    """Multi-user attribution: subfolder name when present, else current OS user.

    The first folder component's ``__opts`` suffix is stripped so submitter
    matches even when the folder also encodes per-job options.
    """
    try:
        relative = path.relative_to(watch_dir)
    except ValueError:
        return _local_user()
    if len(relative.parts) <= 1:
        return _local_user()
    head = relative.parts[0]
    name_part, _ = split_label(head)
    return name_part or _local_user()


def _sides_label(value: str | None) -> str:
    if not value:
        return "default"
    return {"simplex": "single", "duplex": "duplex (long)", "duplexshort": "duplex (short)"}.get(value, value)


def _color_label(value: str | None) -> str:
    if not value:
        return "default"
    return {"color": "color", "monochrome": "mono"}.get(value, value)


# ---------------------------------------------------------------------------
# Printer enumeration (Windows PowerShell)
# ---------------------------------------------------------------------------

def list_printers() -> list[str]:
    """Return Windows printer names via PowerShell. Empty list on failure."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-Printer).Name"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("could not enumerate printers: %s", exc)
        return []
    if result.returncode != 0:
        log.warning("Get-Printer exit=%s stderr=%s", result.returncode, result.stderr.strip())
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# History store
# ---------------------------------------------------------------------------

class HistoryStore:
    """Persistent record of past print jobs in ``%APPDATA%\\PrintWatcher\\history.json``."""

    MAX_ENTRIES = 200

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._records: list[PrintRecord] = self._load()

    def _load(self) -> list[PrintRecord]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("history load failed: %s", exc)
            return []
        out: list[PrintRecord] = []
        for entry in data[-self.MAX_ENTRIES:] if isinstance(data, list) else []:
            if not isinstance(entry, dict):
                continue
            try:
                out.append(PrintRecord(**entry))
            except TypeError:
                continue
        return out

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps([asdict(r) for r in self._records], indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._path)
        except OSError as exc:
            log.warning("history save failed: %s", exc)

    def append(self, record: PrintRecord) -> None:
        with self._lock:
            self._records.append(record)
            if len(self._records) > self.MAX_ENTRIES:
                self._records = self._records[-self.MAX_ENTRIES:]
            self._save()

    def recent(self) -> list[PrintRecord]:
        with self._lock:
            return list(reversed(self._records))

    def clear(self) -> None:
        with self._lock:
            self._records = []
            self._save()


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def _wait_until_stable(path: Path) -> bool:
    last = -1
    stable = 0
    while stable < STABLE_CHECKS:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False
        if size == last and size > 0:
            stable += 1
        else:
            stable = 0
            last = size
        time.sleep(STABLE_INTERVAL_SEC)
    return True


def _unique_target(printed_dir: Path, name: str) -> Path:
    target = printed_dir / name
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    return printed_dir / f"{stem}-{int(time.time())}{suffix}"


# ---------------------------------------------------------------------------
# Printer worker
# ---------------------------------------------------------------------------

class PrinterWorker(threading.Thread):
    """Single-threaded queue so concurrent submits don't collide on the printer."""

    def __init__(
        self,
        sumatra: Path,
        watch_dir: Path,
        printed_dir: Path,
        log_cb: Callable[[str], None],
        stat_cb: Callable[[str, int], None],
        options_provider: Callable[[], PrintOptions],
        history_cb: Callable[[PrintRecord], None],
    ) -> None:
        super().__init__(daemon=True, name="PrinterWorker")
        self._sumatra = sumatra
        self._watch_dir = watch_dir
        self._printed_dir = printed_dir
        self._log = log_cb
        self._stat = stat_cb
        self._options_provider = options_provider
        self._record_history = history_cb
        self._queue: queue.Queue[Path] = queue.Queue()
        self._inflight: set[Path] = set()
        self._lock = threading.Lock()
        self.paused = threading.Event()

    @property
    def inflight_paths(self) -> tuple[Path, ...]:
        with self._lock:
            return tuple(self._inflight)

    def submit(self, path: Path) -> None:
        with self._lock:
            if path in self._inflight:
                return
            self._inflight.add(path)
        self._queue.put(path)
        self._stat("pending", 1)
        self._log(f"queued: {path.name}")

    def run(self) -> None:
        while True:
            path = self._queue.get()
            try:
                self._print_one(path)
            except Exception:  # pragma: no cover - last-resort guard
                log.exception("Unhandled error printing %s", path)
                self._stat("errors", 1)
            finally:
                self._stat("pending", -1)
                with self._lock:
                    self._inflight.discard(path)

    def _print_one(self, path: Path) -> None:
        if self.paused.is_set():
            self._log(f"paused, skipping: {path.name}")
            return
        if not path.exists():
            return
        if not _wait_until_stable(path):
            self._log(f"file never stabilised: {path.name}")
            self._stat("errors", 1)
            self._record(path, "error", "never stabilised", self._options_provider())
            return

        ui_options = self._options_provider()
        options, applied_tokens, _resolved_submitter = resolve_path_options(
            path, self._watch_dir, ui_options,
        )
        printer_label = options.printer or DEFAULT_PRINTER_LABEL
        details = [f"to {printer_label}"]
        if options.copies > 1:
            details.append(f"{options.copies} copies")
        if options.sides:
            details.append(_sides_label(options.sides))
        if options.color:
            details.append(_color_label(options.color))
        if applied_tokens:
            details.append(f"path overrides: {', '.join(applied_tokens)}")
        self._log(f"printing: {path.name} ({', '.join(details)})")

        try:
            result = subprocess.run(
                options.to_sumatra_args(self._sumatra, path),
                check=False,
            )
        except FileNotFoundError:
            self._log(f"SumatraPDF not found at {self._sumatra}")
            self._stat("errors", 1)
            self._record(path, "error", f"SumatraPDF missing: {self._sumatra}", options)
            return
        except OSError as exc:
            self._log(f"launch failed for {path.name}: {exc}")
            self._stat("errors", 1)
            self._record(path, "error", f"launch failed: {exc}", options)
            return

        if result.returncode != 0:
            self._log(f"sumatra exit={result.returncode}: {path.name}")
            self._stat("errors", 1)
            self._record(path, "error", f"sumatra exit={result.returncode}", options)
            return

        try:
            submitter = _submitter_for(path, self._watch_dir)
            dest_dir = self._printed_dir / submitter if submitter != _local_user() or path.parent != self._watch_dir else self._printed_dir
            dest_dir.mkdir(parents=True, exist_ok=True)
            target = _unique_target(dest_dir, path.name)
            path.rename(target)
            self._log(f"done: {path.name}")
            self._stat("printed", 1)
            self._record(path, "ok", "", options, submitter=submitter)
        except OSError as exc:
            self._log(f"move failed for {path.name}: {exc}")
            self._stat("errors", 1)
            self._record(path, "error", f"move failed: {exc}", options)

    def _record(
        self,
        path: Path,
        status: str,
        detail: str,
        options: PrintOptions,
        submitter: str | None = None,
    ) -> None:
        self._record_history(
            PrintRecord(
                timestamp=datetime.now().isoformat(timespec="seconds"),
                filename=path.name,
                status=status,
                detail=detail,
                printer=options.printer or "default",
                copies=options.copies,
                sides=_sides_label(options.sides),
                color=_color_label(options.color),
                submitter=submitter or _submitter_for(path, self._watch_dir),
            )
        )


# ---------------------------------------------------------------------------
# Filesystem watcher
# ---------------------------------------------------------------------------

class InboxHandler(FileSystemEventHandler):
    """Filesystem event handler — forwards eligible files to a dispatch callback."""

    def __init__(
        self,
        watch_dir: Path,
        printed_dir: Path,
        dispatch: Callable[[Path], None],
    ) -> None:
        self._watch_dir = watch_dir
        self._printed_dir = printed_dir
        self._dispatch = dispatch

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._maybe_submit(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._maybe_submit(event.dest_path)

    def _maybe_submit(self, raw_path: str) -> None:
        path = Path(raw_path)
        if path.suffix.lower() not in EXTS:
            return
        try:
            relative = path.relative_to(self._watch_dir)
        except ValueError:
            return
        if not relative.parts:
            return
        if relative.parts[0] in RESERVED_TOP_LEVEL:
            return
        if self._printed_dir in path.parents:
            return
        if not path.is_file():
            return
        self._dispatch(path)


def _poll_inbox(
    watch_dir: Path,
    dispatch: Callable[[Path], None],
    stop: threading.Event,
) -> None:
    printed_dir = watch_dir / PRINTED_SUBDIR
    skipped_dir = watch_dir / SKIPPED_SUBDIR
    scheduled_dir = watch_dir / SCHEDULED_SUBDIR
    reserved_roots = (printed_dir, skipped_dir, scheduled_dir)
    while not stop.is_set():
        try:
            for entry in watch_dir.rglob("*"):
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in EXTS:
                    continue
                if any(root in entry.parents or entry.parent == root for root in reserved_roots):
                    continue
                dispatch(entry)
        except FileNotFoundError:
            pass
        stop.wait(POLL_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# Theme palettes (read by both Tk UI and FastAPI /api/themes)
# ---------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    "Ocean": {
        "BG": "#006494", "PANEL": "#0582ca", "LOG_BG": "#003e5c",
        "TEXT": "#e0f2ff", "MUTED": "#a3c4d9",
        "OK": "#00a6fb", "ERR": "#6b8a9c",
        "LOG_TEXT": "#e0f2ff", "BTN_HOVER": "#0a96e0",
    },
    "Forest": {
        "BG": "#0a210f", "PANEL": "#14591d", "LOG_BG": "#04140a",
        "TEXT": "#e1e289", "MUTED": "#b8b370",
        "OK": "#99aa38", "ERR": "#acd2ed",
        "LOG_TEXT": "#e1e289", "BTN_HOVER": "#1d7028",
    },
    "Indigo": {
        "BG": "#2e294e", "PANEL": "#3a345e", "LOG_BG": "#1f1c36",
        "TEXT": "#f5fbef", "MUTED": "#9a879d",
        "OK": "#129490", "ERR": "#7a3b69",
        "LOG_TEXT": "#d4cdd6", "BTN_HOVER": "#4a4470",
    },
    "Blush": {
        "BG": "#d9bdc5", "PANEL": "#e9d4da", "LOG_BG": "#fff5f8",
        "TEXT": "#1a3550", "MUTED": "#5b6976",
        "OK": "#548c2f", "ERR": "#78c3fb",
        "LOG_TEXT": "#1a3550", "BTN_HOVER": "#c9adb5",
    },
    "Glass": {
        "BG": "#f2f4f8", "PANEL": "#ffffff", "LOG_BG": "#fafbfc",
        "TEXT": "#1d1d1f", "MUTED": "#6e6e73",
        "OK": "#0a84ff", "ERR": "#ff453a",
        "LOG_TEXT": "#1d1d1f", "BTN_HOVER": "#e5e5ea",
    },
}
DEFAULT_THEME = "Ocean"


# ---------------------------------------------------------------------------
# Preferences (theme + a11y toggles)
# ---------------------------------------------------------------------------

def _preferences_path() -> Path:
    base = os.environ.get("APPDATA")
    return (
        Path(base) / "PrintWatcher" / "preferences.json"
        if base else Path.home() / ".printwatcher" / "preferences.json"
    )


def load_preferences() -> dict:
    path = _preferences_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_preferences(prefs: dict) -> None:
    path = _preferences_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("could not save preferences: %s", exc)


# ---------------------------------------------------------------------------
# WatcherCore — facade owning Observer + Worker + History + state
# ---------------------------------------------------------------------------

@dataclass
class WatcherStats:
    printed: int = 0
    today: int = 0
    pending: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "printed": self.printed,
            "today": self.today,
            "pending": self.pending,
            "errors": self.errors,
        }


# Subscriber callbacks. Each one is best-effort: a raised exception is logged
# and the rest of the subscribers still get the event.
_LogSub = Callable[[str], None]
_StatSub = Callable[[str, int, int], None]   # key, delta, new_value
_HistorySub = Callable[[PrintRecord], None]
_PendingSub = Callable[[tuple[Path, ...]], None]


class WatcherCore:
    """Bundles the Observer, PrinterWorker, and HistoryStore behind one facade.

    Both the legacy Tk UI and the FastAPI backend construct a single
    ``WatcherCore`` and subscribe to its log/stat/history/pending events.
    """

    def __init__(
        self,
        watch_dir: Path,
        sumatra: Path,
        history_path: Path | None = None,
    ) -> None:
        self._watch_dir = watch_dir
        self._sumatra = sumatra
        self._printed_dir = watch_dir / PRINTED_SUBDIR
        self._printed_dir.mkdir(parents=True, exist_ok=True)
        watch_dir.mkdir(parents=True, exist_ok=True)

        self._stats = WatcherStats()
        self._stats_lock = threading.Lock()
        self._stop = threading.Event()
        self._observer: Observer | None = None
        self._poll_thread: threading.Thread | None = None
        self._options = PrintOptions()
        self._options_lock = threading.Lock()

        self._history = HistoryStore(history_path or default_history_path())
        recent = self._history.recent()
        self._stats.printed = sum(1 for r in recent if r.status == "ok")
        self._stats.errors = sum(1 for r in recent if r.status == "error")
        today_iso = datetime.now().date().isoformat()
        self._stats.today = sum(
            1 for r in recent
            if r.status == "ok" and r.timestamp.startswith(today_iso)
        )

        self._log_subs: list[_LogSub] = []
        self._stat_subs: list[_StatSub] = []
        self._history_subs: list[_HistorySub] = []
        self._pending_subs: list[_PendingSub] = []

        self._worker = PrinterWorker(
            sumatra=sumatra,
            watch_dir=watch_dir,
            printed_dir=self._printed_dir,
            log_cb=self._dispatch_log,
            stat_cb=self._dispatch_stat,
            options_provider=self.get_options,
            history_cb=self._dispatch_history,
        )
        self._handler = InboxHandler(
            watch_dir=watch_dir,
            printed_dir=self._printed_dir,
            dispatch=self._submit_path,
        )

    # ----- public properties -------------------------------------------------

    @property
    def watch_dir(self) -> Path:
        return self._watch_dir

    @property
    def sumatra(self) -> Path:
        return self._sumatra

    @property
    def history(self) -> HistoryStore:
        return self._history

    @property
    def worker(self) -> PrinterWorker:
        return self._worker

    @property
    def stats(self) -> dict[str, int]:
        with self._stats_lock:
            return self._stats.as_dict()

    @property
    def is_paused(self) -> bool:
        return self._worker.paused.is_set()

    def get_options(self) -> PrintOptions:
        with self._options_lock:
            return self._options

    def set_options(self, options: PrintOptions) -> None:
        with self._options_lock:
            self._options = options

    def pending_paths(self) -> tuple[Path, ...]:
        return self._worker.inflight_paths

    # ----- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Start the worker, observer, and rescan polling thread."""
        if not self._worker.is_alive():
            self._worker.start()
        self._observer = Observer()
        self._observer.schedule(self._handler, str(self._watch_dir), recursive=True)
        self._observer.start()
        self._poll_thread = threading.Thread(
            target=_poll_inbox,
            args=(self._watch_dir, self._submit_path, self._stop),
            daemon=True,
            name="InboxRescan",
        )
        self._poll_thread.start()
        self._dispatch_log(f"watching: {self._watch_dir}")

    def stop(self) -> None:
        """Stop watching. The worker thread is daemon and exits with the process."""
        self._stop.set()
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:  # pragma: no cover - shutdown best effort
                log.exception("observer stop failed")
            finally:
                self._observer = None

    def pause(self) -> None:
        self._worker.paused.set()
        self._dispatch_log("paused")

    def resume(self) -> None:
        self._worker.paused.clear()
        self._dispatch_log("resumed")

    def set_paused(self, paused: bool) -> bool:
        if paused:
            self.pause()
        else:
            self.resume()
        return self.is_paused

    # ----- subscriptions -----------------------------------------------------

    def subscribe_log(self, cb: _LogSub) -> Callable[[], None]:
        self._log_subs.append(cb)
        return lambda: self._log_subs.remove(cb) if cb in self._log_subs else None

    def subscribe_stat(self, cb: _StatSub) -> Callable[[], None]:
        self._stat_subs.append(cb)
        return lambda: self._stat_subs.remove(cb) if cb in self._stat_subs else None

    def subscribe_history(self, cb: _HistorySub) -> Callable[[], None]:
        self._history_subs.append(cb)
        return lambda: self._history_subs.remove(cb) if cb in self._history_subs else None

    def subscribe_pending(self, cb: _PendingSub) -> Callable[[], None]:
        self._pending_subs.append(cb)
        return lambda: self._pending_subs.remove(cb) if cb in self._pending_subs else None

    # ----- internal dispatch -------------------------------------------------

    def _submit_path(self, path: Path) -> None:
        self._worker.submit(path)
        self._dispatch_pending()

    def _dispatch_log(self, line: str) -> None:
        for cb in tuple(self._log_subs):
            try:
                cb(line)
            except Exception:  # pragma: no cover - subscriber bug
                log.exception("log subscriber raised")

    def _dispatch_stat(self, key: str, delta: int) -> None:
        with self._stats_lock:
            current = getattr(self._stats, key, 0) + delta
            setattr(self._stats, key, max(0, current))
            new_value = getattr(self._stats, key)
        for cb in tuple(self._stat_subs):
            try:
                cb(key, delta, new_value)
            except Exception:  # pragma: no cover - subscriber bug
                log.exception("stat subscriber raised")
        if key == "pending":
            self._dispatch_pending()

    def _dispatch_history(self, record: PrintRecord) -> None:
        self._history.append(record)
        for cb in tuple(self._history_subs):
            try:
                cb(record)
            except Exception:  # pragma: no cover - subscriber bug
                log.exception("history subscriber raised")

    def _dispatch_pending(self) -> None:
        items = self._worker.inflight_paths
        for cb in tuple(self._pending_subs):
            try:
                cb(items)
            except Exception:  # pragma: no cover - subscriber bug
                log.exception("pending subscriber raised")
