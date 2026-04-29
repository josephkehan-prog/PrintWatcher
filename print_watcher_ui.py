r"""PrintWatcher with a desktop UI.

A small Tkinter window showing live status, stats, and a scrollable event log.
Adds two reliability fixes over the tray version:

1. Listens for `on_moved` as well as `on_created` (OneDrive often delivers
   files via a temp-file rename, which only fires `on_moved`).
2. Periodically rescans the inbox folder so any file the OS event stream
   misses still gets printed.

Run directly:

    python print_watcher_ui.py

Paths are auto-detected from `print_watcher_tray.py` (which `bootstrap.ps1`
patches with the per-machine inbox + SumatraPDF locations) and fall back to
`%OneDrive%\PrintInbox` and `C:\Tools\SumatraPDF\SumatraPDF.exe`.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

APP_VERSION = "0.2.0"

EXTS = frozenset({".pdf", ".png", ".jpg", ".jpeg"})
POLL_INTERVAL_SEC = 5.0
STABLE_CHECKS = 3
STABLE_INTERVAL_SEC = 1.0
LOG_LINE_LIMIT = 500
PRINTED_SUBDIR = "_printed"

DEFAULT_SUMATRA = Path(r"C:\Tools\SumatraPDF\SumatraPDF.exe")


def _logs_dir() -> Path:
    base = os.environ.get("APPDATA")
    return Path(base) / "PrintWatcher" / "logs" if base else Path.home() / ".printwatcher" / "logs"

DEFAULT_PRINTER_LABEL = "Windows default printer"
SIDES_CHOICES = (
    ("Printer default", None),
    ("Single-sided (simplex)", "simplex"),
    ("Duplex (long edge)", "duplex"),
    ("Duplex (short edge)", "duplexshort"),
)
COLOR_CHOICES = (
    ("Printer default", None),
    ("Color", "color"),
    ("Monochrome", "monochrome"),
)

log = logging.getLogger("printwatcher.ui")


@dataclass(frozen=True)
class PrintOptions:
    """Per-job print settings applied to every file the watcher prints next."""

    printer: str | None = None  # None = Windows default
    copies: int = 1
    sides: str | None = None    # None | "simplex" | "duplex" | "duplexshort"
    color: str | None = None    # None | "color" | "monochrome"

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

    timestamp: str          # ISO 8601 (local time) for human display
    filename: str
    status: str             # "ok" | "error"
    detail: str = ""        # short note (sumatra exit, move failure, etc.)
    printer: str = ""       # display label, "" means default
    copies: int = 1
    sides: str = ""         # display label
    color: str = ""         # display label
    submitter: str = ""     # subfolder name, or current Windows user for root drops

    @property
    def time_short(self) -> str:
        try:
            return datetime.fromisoformat(self.timestamp).strftime("%m/%d %H:%M")
        except ValueError:
            return self.timestamp


class HistoryStore:
    """Persistent record of past print jobs in %APPDATA%\\PrintWatcher\\history.json."""

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


def default_history_path() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "PrintWatcher" / "history.json"
    return Path.home() / ".printwatcher" / "history.json"


FILENAME_OPTIONS_SEPARATOR = "__"
FILENAME_TOKEN_SPLIT = re.compile(r"[,_\s]+")


def _apply_option_tokens(opt_str: str, base: "PrintOptions") -> tuple["PrintOptions", list[str]]:
    """Parse a `copies=3_duplex_color`-style token list into an option overlay."""
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
            # Printer choice intentionally not supported via filename — names
            # often contain spaces, which collide with the token separator.
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
    """Split `<name>__<options>` into (name, opt_str). Either may be empty."""
    if FILENAME_OPTIONS_SEPARATOR not in label:
        return label, ""
    name_part, _, opt_str = label.rpartition(FILENAME_OPTIONS_SEPARATOR)
    return name_part, opt_str


def parse_filename_options(filename: str, base: "PrintOptions") -> tuple["PrintOptions", list[str]]:
    """Overlay options encoded in the filename suffix `__copies=3_duplex_color`."""
    stem = Path(filename).stem
    name_part, opt_str = split_label(stem)
    if not opt_str or not name_part:
        return base, []
    return _apply_option_tokens(opt_str, base)


def resolve_path_options(
    path: Path,
    watch_dir: Path,
    base: "PrintOptions",
) -> tuple["PrintOptions", list[str], str]:
    """Walk every path component under watch_dir and accumulate option overlays.

    Returns (merged_options, applied_tokens, submitter). The first folder
    component's name (with any `__opts` suffix stripped) determines the
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

    # Folder components (everything but the trailing filename)
    for index, part in enumerate(parts[:-1]):
        name_part, opt_str = split_label(part)
        if index == 0 and name_part:
            submitter = name_part
        if opt_str:
            options, tokens = _apply_option_tokens(opt_str, options)
            applied.extend(tokens)

    # Filename suffix overlay (highest priority)
    filename_stem = Path(parts[-1]).stem
    name_part, opt_str = split_label(filename_stem)
    if opt_str and name_part:
        options, tokens = _apply_option_tokens(opt_str, options)
        applied.extend(tokens)

    return options, applied, submitter


def _local_user() -> str:
    return (
        os.environ.get("USERNAME")
        or os.environ.get("USER")
        or "local"
    )


def _submitter_for(path: Path, watch_dir: Path) -> str:
    """Multi-user attribution: subfolder name when present, else current OS user.

    The first folder component's `__opts` suffix is stripped so submitter
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


def discover_paths() -> tuple[Path, Path]:
    """Return (watch_dir, sumatra_exe), preferring a sibling tray script."""
    watch_dir: Path | None = None
    sumatra: Path | None = None

    sibling = Path(__file__).resolve().parent / "print_watcher_tray.py"
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


# ---------------------------------------------------------------------------
# Print queue worker
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
    def __init__(self, watch_dir: Path, printed_dir: Path, worker: PrinterWorker) -> None:
        self._watch_dir = watch_dir
        self._printed_dir = printed_dir
        self._worker = worker

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
        if relative.parts[0] == PRINTED_SUBDIR:
            return
        if self._printed_dir in path.parents:
            return
        if not path.is_file():
            return
        self._worker.submit(path)


def _poll_inbox(watch_dir: Path, worker: PrinterWorker, stop: threading.Event) -> None:
    printed_dir = watch_dir / PRINTED_SUBDIR
    while not stop.is_set():
        try:
            for entry in watch_dir.rglob("*"):
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in EXTS:
                    continue
                if printed_dir in entry.parents or entry.parent == printed_dir:
                    continue
                worker.submit(entry)
        except FileNotFoundError:
            pass
        stop.wait(POLL_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

# Palette presets. Each key maps to a dict of role → hex. Switched at
# runtime via the View → Theme menu; selection persists in
# %APPDATA%/PrintWatcher/preferences.json.
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
}
DEFAULT_THEME = "Ocean"

# Module-level color names update when the theme changes.
COLOR_BG = THEMES[DEFAULT_THEME]["BG"]
COLOR_PANEL = THEMES[DEFAULT_THEME]["PANEL"]
COLOR_LOG_BG = THEMES[DEFAULT_THEME]["LOG_BG"]
COLOR_TEXT = THEMES[DEFAULT_THEME]["TEXT"]
COLOR_MUTED = THEMES[DEFAULT_THEME]["MUTED"]
COLOR_OK = THEMES[DEFAULT_THEME]["OK"]
COLOR_ERR = THEMES[DEFAULT_THEME]["ERR"]
COLOR_LOG_TEXT = THEMES[DEFAULT_THEME]["LOG_TEXT"]
COLOR_BTN_HOVER = THEMES[DEFAULT_THEME]["BTN_HOVER"]


def _apply_theme(name: str) -> None:
    """Update module-level color constants from THEMES[name]."""
    global COLOR_BG, COLOR_PANEL, COLOR_LOG_BG, COLOR_TEXT, COLOR_MUTED
    global COLOR_OK, COLOR_ERR, COLOR_LOG_TEXT, COLOR_BTN_HOVER
    palette = THEMES.get(name) or THEMES[DEFAULT_THEME]
    COLOR_BG = palette["BG"]
    COLOR_PANEL = palette["PANEL"]
    COLOR_LOG_BG = palette["LOG_BG"]
    COLOR_TEXT = palette["TEXT"]
    COLOR_MUTED = palette["MUTED"]
    COLOR_OK = palette["OK"]
    COLOR_ERR = palette["ERR"]
    COLOR_LOG_TEXT = palette["LOG_TEXT"]
    COLOR_BTN_HOVER = palette["BTN_HOVER"]


def _preferences_path() -> Path:
    base = os.environ.get("APPDATA")
    return Path(base) / "PrintWatcher" / "preferences.json" if base else Path.home() / ".printwatcher" / "preferences.json"


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


class App(tk.Tk):
    def __init__(self, watch_dir: Path, sumatra: Path) -> None:
        super().__init__()
        self._watch_dir = watch_dir
        self._sumatra = sumatra
        self._printed_dir = watch_dir / PRINTED_SUBDIR
        self._printed_dir.mkdir(parents=True, exist_ok=True)
        watch_dir.mkdir(parents=True, exist_ok=True)

        self._stats = {"printed": 0, "pending": 0, "errors": 0}
        self._stop = threading.Event()
        self._observer: Observer | None = None
        self._print_options = PrintOptions()
        self._history = HistoryStore(default_history_path())
        self._stats["printed"] = sum(1 for r in self._history.recent() if r.status == "ok")
        self._stats["errors"] = sum(1 for r in self._history.recent() if r.status == "error")

        self._preferences = load_preferences()
        self._theme_name = self._preferences.get("theme", DEFAULT_THEME)
        if self._theme_name not in THEMES:
            self._theme_name = DEFAULT_THEME
        _apply_theme(self._theme_name)
        self._tray_icon = None
        self._sort_state: dict[str, bool] = {}     # column -> reverse?

        self.title("PrintWatcher")
        self.geometry("960x680")
        self.minsize(720, 560)
        self.configure(bg=COLOR_BG)
        self._set_window_icon()

        self._build_menu_bar()
        self._build_ui()
        self._bind_keyboard_shortcuts()
        self._refresh_history()

        self._worker = PrinterWorker(
            sumatra=sumatra,
            watch_dir=self._watch_dir,
            printed_dir=self._printed_dir,
            log_cb=self._log_threadsafe,
            stat_cb=self._stat_threadsafe,
            options_provider=lambda: self._print_options,
            history_cb=self._record_threadsafe,
        )
        self._worker.start()
        self._start_observer()
        threading.Thread(
            target=_poll_inbox,
            args=(self._watch_dir, self._worker, self._stop),
            daemon=True,
            name="InboxPoller",
        ).start()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._log_threadsafe(f"watching {watch_dir}")
        if not sumatra.exists():
            self._log_threadsafe(f"WARNING: SumatraPDF missing at {sumatra}")

    # ---- layout -------------------------------------------------------

    def _build_ui(self) -> None:
        self._init_styles()
        self._build_hero()
        self._build_options_panel()
        self._build_tabs()
        self._build_action_bar()

    def _init_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Action.TButton",
            background=COLOR_PANEL,
            foreground=COLOR_TEXT,
            borderwidth=0,
            padding=(14, 8),
            font=("Segoe UI", 10),
        )
        style.map(
            "Action.TButton",
            background=[("active", COLOR_BTN_HOVER)],
            foreground=[("active", COLOR_TEXT)],
        )
        style.configure(
            "Pause.TButton",
            background=COLOR_OK,
            foreground=COLOR_BG,
            borderwidth=0,
            padding=(16, 8),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Pause.TButton",
            background=[("active", COLOR_BTN_HOVER)],
        )
        style.configure(
            "App.TNotebook",
            background=COLOR_BG,
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "App.TNotebook.Tab",
            background=COLOR_BG,
            foreground=COLOR_MUTED,
            padding=(18, 8),
            font=("Segoe UI", 10),
            borderwidth=0,
        )
        style.map(
            "App.TNotebook.Tab",
            background=[("selected", COLOR_PANEL)],
            foreground=[("selected", COLOR_TEXT)],
            expand=[("selected", (0, 0, 0, 0))],
        )
        style.configure(
            "App.Treeview",
            background=COLOR_LOG_BG,
            fieldbackground=COLOR_LOG_BG,
            foreground=COLOR_LOG_TEXT,
            rowheight=26,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure(
            "App.Treeview.Heading",
            background=COLOR_PANEL,
            foreground=COLOR_TEXT,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padding=(8, 6),
        )
        style.map("App.Treeview.Heading", background=[("active", COLOR_BTN_HOVER)])

    def _build_hero(self) -> None:
        hero = tk.Frame(self, bg=COLOR_BG, padx=22, pady=18)
        hero.pack(fill="x")

        title = tk.Frame(hero, bg=COLOR_BG)
        title.pack(fill="x")

        self._dot = tk.Canvas(title, width=18, height=18, bg=COLOR_BG, highlightthickness=0)
        self._dot.pack(side="left", pady=(4, 0))
        self._set_dot(COLOR_OK)

        wordmark = tk.Frame(title, bg=COLOR_BG)
        wordmark.pack(side="left", padx=(12, 0))

        tk.Label(
            wordmark, text="PrintWatcher", fg=COLOR_TEXT, bg=COLOR_BG,
            font=("Segoe UI Semibold", 18),
        ).pack(anchor="w")
        self._status_label = tk.Label(
            wordmark, text="Active · watching for new files", fg=COLOR_MUTED,
            bg=COLOR_BG, font=("Segoe UI", 10),
        )
        self._status_label.pack(anchor="w", pady=(2, 0))

        self._pause_btn = ttk.Button(
            title, text="Pause", style="Pause.TButton", command=self._toggle_pause,
        )
        self._pause_btn.pack(side="right", anchor="n")

        path_label = tk.Label(
            hero, text=str(self._watch_dir), fg=COLOR_MUTED, bg=COLOR_BG,
            font=("Segoe UI", 9),
        )
        path_label.pack(anchor="w", pady=(10, 12))

        stats = tk.Frame(hero, bg=COLOR_BG)
        stats.pack(fill="x")
        self._stat_labels: dict[str, tk.Label] = {}
        cells = (("printed", "Printed"), ("pending", "In queue"), ("errors", "Errors"))
        for idx, (key, label) in enumerate(cells):
            cell = tk.Frame(stats, bg=COLOR_PANEL, padx=18, pady=14)
            cell.grid(row=0, column=idx, sticky="ew", padx=(0 if idx == 0 else 10, 0))
            stats.grid_columnconfigure(idx, weight=1, uniform="stat")
            tk.Label(
                cell, text=label.upper(), fg=COLOR_MUTED, bg=COLOR_PANEL,
                font=("Segoe UI", 8, "bold"),
            ).pack(anchor="w")
            value = tk.Label(
                cell, text=str(self._stats[key]), fg=COLOR_TEXT, bg=COLOR_PANEL,
                font=("Segoe UI Semibold", 22),
            )
            value.pack(anchor="w", pady=(4, 0))
            self._stat_labels[key] = value

    def _build_tabs(self) -> None:
        wrap = tk.Frame(self, bg=COLOR_BG, padx=22, pady=8)
        wrap.pack(fill="both", expand=True)
        notebook = ttk.Notebook(wrap, style="App.TNotebook")
        notebook.pack(fill="both", expand=True)

        # Activity tab
        activity = tk.Frame(notebook, bg=COLOR_PANEL)
        notebook.add(activity, text="Activity")
        log_inner = tk.Frame(activity, bg=COLOR_PANEL, padx=2, pady=2)
        log_inner.pack(fill="both", expand=True)
        self._log_text = tk.Text(
            log_inner,
            bg=COLOR_LOG_BG,
            fg=COLOR_LOG_TEXT,
            insertbackground=COLOR_LOG_TEXT,
            font=("Consolas", 10),
            wrap="none",
            relief="flat",
            padx=12,
            pady=10,
        )
        self._log_text.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(log_inner, orient="vertical", command=self._log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self._log_text.configure(yscrollcommand=log_scroll.set, state="disabled")

        # History tab
        history = tk.Frame(notebook, bg=COLOR_PANEL)
        notebook.add(history, text="History")

        filter_bar = tk.Frame(history, bg=COLOR_PANEL, padx=10, pady=8)
        filter_bar.pack(fill="x")
        tk.Label(
            filter_bar, text="Filter", fg=COLOR_MUTED, bg=COLOR_PANEL,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(0, 8))
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._refresh_history())
        ttk.Entry(filter_bar, textvariable=self._filter_var).pack(
            side="left", fill="x", expand=True,
        )
        tk.Label(
            filter_bar, text="right-click a row for actions",
            fg=COLOR_MUTED, bg=COLOR_PANEL, font=("Segoe UI", 8, "italic"),
        ).pack(side="right", padx=(8, 0))

        tree_inner = tk.Frame(history, bg=COLOR_PANEL, padx=2, pady=2)
        tree_inner.pack(fill="both", expand=True)
        columns = ("time", "submitter", "file", "status", "printer", "copies", "sides", "color")
        self._history_tree = ttk.Treeview(
            tree_inner, columns=columns, show="headings", style="App.Treeview",
        )
        headings = {
            "time": ("Time", 110),
            "submitter": ("Submitter", 110),
            "file": ("File", 240),
            "status": ("Status", 70),
            "printer": ("Printer", 150),
            "copies": ("Copies", 60),
            "sides": ("Sides", 110),
            "color": ("Color", 80),
        }
        for col, (label, width) in headings.items():
            self._history_tree.heading(
                col, text=label,
                command=lambda c=col: self._sort_history_by(c),
            )
            anchor = "e" if col == "copies" else "w"
            self._history_tree.column(col, width=width, anchor=anchor, stretch=(col == "file"))
        self._history_tree.tag_configure("ok", foreground=COLOR_OK)
        self._history_tree.tag_configure("error", foreground=COLOR_ERR)
        self._history_tree.pack(side="left", fill="both", expand=True)
        tree_scroll = ttk.Scrollbar(tree_inner, orient="vertical", command=self._history_tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self._history_tree.configure(yscrollcommand=tree_scroll.set)

        self._build_history_context_menu()

    def _build_action_bar(self) -> None:
        bar = tk.Frame(self, bg=COLOR_BG, padx=22, pady=14)
        bar.pack(fill="x")
        ttk.Button(bar, text="Open inbox", style="Action.TButton",
                   command=lambda: self._open_folder(self._watch_dir)).pack(side="left")
        ttk.Button(bar, text="Open printed", style="Action.TButton",
                   command=lambda: self._open_folder(self._printed_dir)).pack(side="left", padx=8)
        ttk.Button(bar, text="Rescan now", style="Action.TButton",
                   command=self._rescan_now).pack(side="left", padx=8)
        ttk.Button(bar, text="Clear log", style="Action.TButton",
                   command=self._clear_log).pack(side="left", padx=8)
        ttk.Button(bar, text="Clear history", style="Action.TButton",
                   command=self._clear_history).pack(side="left", padx=8)
        ttk.Button(bar, text="Quit", style="Action.TButton",
                   command=self._on_close).pack(side="right")

    def _set_dot(self, color: str) -> None:
        self._dot.delete("all")
        # Outer halo + filled center for a softer pill look
        self._dot.create_oval(0, 0, 18, 18, fill=color, outline=color)
        self._dot.create_oval(5, 5, 13, 13, fill=COLOR_BG, outline="")
        self._dot.create_oval(7, 7, 11, 11, fill=color, outline="")

    # ---- window chrome -----------------------------------------------

    def _set_window_icon(self) -> None:
        icon_ico = Path(__file__).resolve().parent / "assets" / "printwatcher.ico"
        icon_png = Path(__file__).resolve().parent / "assets" / "printwatcher.png"
        try:
            if sys.platform == "win32" and icon_ico.exists():
                self.iconbitmap(default=str(icon_ico))
                return
        except tk.TclError:
            pass
        try:
            if icon_png.exists():
                self._icon_image = tk.PhotoImage(file=str(icon_png))
                self.iconphoto(True, self._icon_image)
        except tk.TclError:
            pass

    def _build_menu_bar(self) -> None:
        menubar = tk.Menu(self)
        self.configure(menu=menubar)

        # File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open inbox\tCtrl+O",
                              command=lambda: self._open_folder(self._watch_dir))
        file_menu.add_command(label="Open printed",
                              command=lambda: self._open_folder(self._printed_dir))
        file_menu.add_command(label="Rescan now\tCtrl+R", command=self._rescan_now)
        file_menu.add_separator()
        file_menu.add_command(label="Hide to tray\tEsc", command=self._hide_to_tray)
        file_menu.add_command(label="Quit\tCtrl+Q", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        # View
        view_menu = tk.Menu(menubar, tearoff=0)
        theme_menu = tk.Menu(view_menu, tearoff=0)
        self._theme_var = tk.StringVar(value=self._theme_name)
        for name in THEMES:
            theme_menu.add_radiobutton(
                label=name, value=name, variable=self._theme_var,
                command=lambda n=name: self._switch_theme(n),
            )
        view_menu.add_cascade(label="Theme", menu=theme_menu)
        view_menu.add_separator()
        view_menu.add_command(label="Pause / Resume\tCtrl+P", command=self._toggle_pause)
        view_menu.add_command(label="Focus filter\tCtrl+F",
                              command=self._focus_filter)
        view_menu.add_command(label="Clear log", command=self._clear_log)
        view_menu.add_command(label="Clear history", command=self._clear_history)
        menubar.add_cascade(label="View", menu=view_menu)

        # Help
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Check for updates", command=self._check_updates)
        help_menu.add_command(label="View logs folder",
                              command=lambda: self._open_folder(_logs_dir()))
        help_menu.add_separator()
        help_menu.add_command(label="About PrintWatcher", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

    def _bind_keyboard_shortcuts(self) -> None:
        bindings = (
            ("<Control-p>", lambda _e: self._toggle_pause()),
            ("<Control-P>", lambda _e: self._toggle_pause()),
            ("<Control-r>", lambda _e: self._rescan_now()),
            ("<Control-R>", lambda _e: self._rescan_now()),
            ("<Control-f>", lambda _e: self._focus_filter()),
            ("<Control-F>", lambda _e: self._focus_filter()),
            ("<Control-o>", lambda _e: self._open_folder(self._watch_dir)),
            ("<Control-O>", lambda _e: self._open_folder(self._watch_dir)),
            ("<Control-q>", lambda _e: self._on_close()),
            ("<Control-Q>", lambda _e: self._on_close()),
            ("<F5>", lambda _e: self._refresh_history()),
            ("<Escape>", lambda _e: self._hide_to_tray()),
        )
        for sequence, handler in bindings:
            self.bind_all(sequence, handler)

    def _focus_filter(self) -> None:
        if hasattr(self, "_filter_var"):
            for widget in self.winfo_children():
                self._descend_focus_filter(widget)

    def _descend_focus_filter(self, widget) -> bool:
        # Hunt for the Entry tied to _filter_var.
        try:
            for child in widget.winfo_children():
                if isinstance(child, ttk.Entry) and child.cget("textvariable") == str(self._filter_var):
                    child.focus_set()
                    child.select_range(0, "end")
                    return True
                if self._descend_focus_filter(child):
                    return True
        except tk.TclError:
            pass
        return False

    # ---- theme switching ---------------------------------------------

    def _switch_theme(self, name: str) -> None:
        if name not in THEMES:
            return
        self._theme_name = name
        _apply_theme(name)
        self._preferences["theme"] = name
        save_preferences(self._preferences)
        self._log_threadsafe(f"theme changed to {name} (full reload on next launch)")
        self._show_modal_message(
            "Theme switched",
            f"Theme set to {name}. Restart PrintWatcher to apply.",
        )

    def _show_modal_message(self, title: str, message: str) -> None:
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=COLOR_BG)
        win.transient(self)
        win.grab_set()
        tk.Label(
            win, text=message, fg=COLOR_TEXT, bg=COLOR_BG,
            font=("Segoe UI", 10), padx=24, pady=18, wraplength=380, justify="left",
        ).pack()
        ttk.Button(win, text="OK", style="Action.TButton", command=win.destroy).pack(pady=(0, 12))
        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{x}+{y}")

    # ---- About ---------------------------------------------------------

    def _show_about(self) -> None:
        win = tk.Toplevel(self)
        win.title("About PrintWatcher")
        win.configure(bg=COLOR_BG)
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)

        body = tk.Frame(win, bg=COLOR_BG, padx=28, pady=22)
        body.pack()
        tk.Label(body, text="PrintWatcher", fg=COLOR_TEXT, bg=COLOR_BG,
                 font=("Segoe UI Semibold", 16)).pack(anchor="w")
        tk.Label(body, text=f"Version {APP_VERSION}", fg=COLOR_MUTED, bg=COLOR_BG,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 12))
        tk.Label(
            body,
            text=(
                "Auto-print files dropped into a OneDrive folder.\n"
                "MIT licensed, no telemetry by default.\n\n"
                f"Inbox: {self._watch_dir}\n"
                f"Sumatra: {self._sumatra}\n"
                f"History: {self._history._path}\n"
                f"Logs: {_logs_dir()}"
            ),
            fg=COLOR_TEXT, bg=COLOR_BG, font=("Consolas", 9),
            justify="left",
        ).pack(anchor="w")
        tk.Label(
            body, text="https://github.com/josephkehan-prog/PrintWatcher",
            fg=COLOR_OK, bg=COLOR_BG, font=("Segoe UI", 9), cursor="hand2",
        ).pack(anchor="w", pady=(12, 0))

        btn_row = tk.Frame(body, bg=COLOR_BG)
        btn_row.pack(anchor="w", pady=(16, 0))
        ttk.Button(btn_row, text="Close", style="Action.TButton",
                   command=win.destroy).pack()

    # ---- self-update check --------------------------------------------

    def _check_updates(self) -> None:
        threading.Thread(target=self._check_updates_async, daemon=True).start()

    def _check_updates_async(self) -> None:
        import urllib.error
        import urllib.request

        url = "https://api.github.com/repos/josephkehan-prog/PrintWatcher/releases/latest"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            self._log_threadsafe(f"update check failed: {exc}")
            return
        latest = (payload.get("tag_name") or "").lstrip("v")
        if not latest:
            self._log_threadsafe("update check: no releases found yet")
            return
        if latest == APP_VERSION:
            self.after(0, self._show_modal_message, "Up to date",
                       f"You're on the latest version (v{APP_VERSION}).")
            return
        url_html = payload.get("html_url") or "https://github.com/josephkehan-prog/PrintWatcher/releases"
        self.after(
            0, self._show_modal_message, "Update available",
            f"v{latest} is available (you're on v{APP_VERSION}).\n\nDownload: {url_html}",
        )

    # ---- tray icon -----------------------------------------------------

    def _hide_to_tray(self) -> None:
        if self._tray_icon is None:
            self._build_tray_icon()
        if self._tray_icon is not None:
            try:
                self.withdraw()
            except tk.TclError:
                pass

    def _show_from_tray(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    def _build_tray_icon(self) -> None:
        try:
            import pystray
            from PIL import Image
        except ImportError:
            self._log_threadsafe("pystray/Pillow not available; cannot hide to tray")
            return
        icon_png = Path(__file__).resolve().parent / "assets" / "printwatcher.png"
        if icon_png.exists():
            image = Image.open(icon_png)
        else:
            image = Image.new("RGB", (64, 64), COLOR_OK)
        menu = pystray.Menu(
            pystray.MenuItem("Show window", lambda _i, _it: self.after(0, self._show_from_tray), default=True),
            pystray.MenuItem("Pause / Resume",
                             lambda _i, _it: self.after(0, self._toggle_pause)),
            pystray.MenuItem("Quit", lambda _i, _it: self.after(0, self._on_close)),
        )
        self._tray_icon = pystray.Icon("PrintWatcher", image, "PrintWatcher", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True, name="TrayIcon").start()

    # ---- print options panel -----------------------------------------

    def _build_options_panel(self) -> None:
        wrap = tk.Frame(self, bg=COLOR_BG, padx=18, pady=4)
        wrap.pack(fill="x")

        panel = tk.Frame(wrap, bg=COLOR_PANEL, padx=14, pady=12)
        panel.pack(fill="x")
        tk.Label(
            panel, text="Print options", fg=COLOR_TEXT, bg=COLOR_PANEL,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        # Row 1: printer dropdown + refresh + copies
        tk.Label(panel, text="Printer", fg=COLOR_MUTED, bg=COLOR_PANEL,
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", padx=(0, 8))
        self._printer_var = tk.StringVar(value=DEFAULT_PRINTER_LABEL)
        self._printer_combo = ttk.Combobox(
            panel, textvariable=self._printer_var, state="readonly", width=42,
        )
        self._printer_combo.grid(row=1, column=1, sticky="ew", padx=(0, 6))
        self._printer_combo.bind("<<ComboboxSelected>>", self._on_printer_change)

        ttk.Button(
            panel, text="Refresh", style="Action.TButton",
            command=self._refresh_printers,
        ).grid(row=1, column=2, padx=(0, 16))

        tk.Label(panel, text="Copies", fg=COLOR_MUTED, bg=COLOR_PANEL,
                 font=("Segoe UI", 9)).grid(row=1, column=3, sticky="e", padx=(0, 6))
        self._copies_var = tk.IntVar(value=1)
        copies_spin = ttk.Spinbox(
            panel, from_=1, to=99, textvariable=self._copies_var, width=5,
            command=self._on_copies_change,
        )
        copies_spin.grid(row=1, column=4, sticky="w")
        copies_spin.bind("<FocusOut>", lambda _e: self._on_copies_change())
        copies_spin.bind("<Return>", lambda _e: self._on_copies_change())

        panel.grid_columnconfigure(1, weight=1)

        # Row 2: sides + color
        tk.Label(panel, text="Sides", fg=COLOR_MUTED, bg=COLOR_PANEL,
                 font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(10, 0))
        self._sides_var = tk.StringVar(value=SIDES_CHOICES[0][0])
        sides_combo = ttk.Combobox(
            panel, textvariable=self._sides_var, state="readonly",
            values=[label for label, _ in SIDES_CHOICES],
        )
        sides_combo.grid(row=2, column=1, sticky="ew", padx=(0, 16), pady=(10, 0))
        sides_combo.bind("<<ComboboxSelected>>", self._on_sides_change)

        tk.Label(panel, text="Color", fg=COLOR_MUTED, bg=COLOR_PANEL,
                 font=("Segoe UI", 9)).grid(row=2, column=3, sticky="e", padx=(0, 6), pady=(10, 0))
        self._color_var = tk.StringVar(value=COLOR_CHOICES[0][0])
        color_combo = ttk.Combobox(
            panel, textvariable=self._color_var, state="readonly", width=14,
            values=[label for label, _ in COLOR_CHOICES],
        )
        color_combo.grid(row=2, column=4, sticky="w", pady=(10, 0))
        color_combo.bind("<<ComboboxSelected>>", self._on_color_change)

        # Row 3: stapling note
        tk.Label(
            panel,
            text=(
                "Stapling / hole-punch: SumatraPDF can't toggle finishing options. "
                "Set them in the printer's driver defaults (Settings -> Printers -> "
                "Printing preferences -> Finishing) or at the device's release dialog."
            ),
            fg=COLOR_MUTED, bg=COLOR_PANEL, font=("Segoe UI", 8),
            wraplength=720, justify="left",
        ).grid(row=3, column=0, columnspan=5, sticky="w", pady=(10, 0))

        self._refresh_printers()

    def _refresh_printers(self) -> None:
        names = list_printers()
        values = [DEFAULT_PRINTER_LABEL] + names
        self._printer_combo.configure(values=values)
        if self._printer_var.get() not in values:
            self._printer_var.set(DEFAULT_PRINTER_LABEL)
            self._print_options = replace(self._print_options, printer=None)
        self._log_threadsafe(f"printer list refreshed ({len(names)} found)")

    def _on_printer_change(self, _event: object = None) -> None:
        choice = self._printer_var.get()
        printer = None if choice == DEFAULT_PRINTER_LABEL else choice
        self._print_options = replace(self._print_options, printer=printer)
        self._log_threadsafe(f"printer set: {choice}")

    def _on_copies_change(self) -> None:
        try:
            value = int(self._copies_var.get())
        except (tk.TclError, ValueError):
            value = 1
        value = max(1, min(99, value))
        self._copies_var.set(value)
        self._print_options = replace(self._print_options, copies=value)
        self._log_threadsafe(f"copies set: {value}")

    def _on_sides_change(self, _event: object = None) -> None:
        label = self._sides_var.get()
        value = next((v for lab, v in SIDES_CHOICES if lab == label), None)
        self._print_options = replace(self._print_options, sides=value)
        self._log_threadsafe(f"sides set: {label}")

    def _on_color_change(self, _event: object = None) -> None:
        label = self._color_var.get()
        value = next((v for lab, v in COLOR_CHOICES if lab == label), None)
        self._print_options = replace(self._print_options, color=value)
        self._log_threadsafe(f"color set: {label}")

    # ---- watcher lifecycle -------------------------------------------

    def _start_observer(self) -> None:
        observer = Observer()
        handler = InboxHandler(self._watch_dir, self._printed_dir, self._worker)
        observer.schedule(handler, str(self._watch_dir), recursive=True)
        observer.start()
        self._observer = observer

    def _on_close(self) -> None:
        self._stop.set()
        if self._observer is not None:
            try:
                self._observer.stop()
            except Exception:
                log.exception("observer stop failed")
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                log.exception("tray icon stop failed")
        self.destroy()

    def _sort_history_by(self, column: str) -> None:
        reverse = self._sort_state.get(column, False)
        self._sort_state[column] = not reverse

        def key_for(record):
            value = getattr(record, column, "")
            if column == "time":
                value = record.timestamp
            elif column == "copies":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    value = 0
            elif isinstance(value, str):
                value = value.lower()
            return value

        records = sorted(self._history.recent(), key=key_for, reverse=reverse)
        # rewrite tree from this ordering, applying current filter
        self._render_history(records)
        # arrow indicator on the heading
        for col in ("time", "submitter", "file", "status", "printer", "copies", "sides", "color"):
            label = self._history_tree.heading(col)["text"].rstrip(" ▲▼")
            if col == column:
                label = f"{label} {'▼' if reverse else '▲'}"
            self._history_tree.heading(col, text=label)

    def _render_history(self, records) -> None:
        filter_text = (
            self._filter_var.get().strip().lower()
            if hasattr(self, "_filter_var") else ""
        )
        for iid in self._history_tree.get_children():
            self._history_tree.delete(iid)
        self._history_row_records = {}
        for record in records:
            if filter_text:
                haystack = " ".join((
                    record.filename, record.submitter,
                    record.printer, record.status, record.detail,
                )).lower()
                if filter_text not in haystack:
                    continue
            status_glyph = "OK" if record.status == "ok" else "FAIL"
            tag = "ok" if record.status == "ok" else "error"
            iid = self._history_tree.insert(
                "", "end",
                values=(
                    record.time_short,
                    record.submitter or "—",
                    record.filename,
                    status_glyph,
                    record.printer,
                    record.copies,
                    record.sides,
                    record.color,
                ),
                tags=(tag,),
            )
            self._history_row_records[iid] = record

    # ---- actions ------------------------------------------------------

    def _toggle_pause(self) -> None:
        if self._worker.paused.is_set():
            self._worker.paused.clear()
            self._status_label.configure(text="Active · watching for new files")
            self._set_dot(COLOR_OK)
            self._pause_btn.configure(text="Pause")
            self._log_threadsafe("resumed")
        else:
            self._worker.paused.set()
            self._status_label.configure(text="Paused · queued jobs are held")
            self._set_dot(COLOR_ERR)
            self._pause_btn.configure(text="Resume")
            self._log_threadsafe("paused")

    def _open_folder(self, path: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            self._log_threadsafe(f"open failed: {exc}")

    def _rescan_now(self) -> None:
        try:
            count = 0
            for entry in self._watch_dir.iterdir():
                if entry.is_file() and entry.suffix.lower() in EXTS:
                    self._worker.submit(entry)
                    count += 1
            self._log_threadsafe(f"manual rescan: {count} candidate(s)")
        except FileNotFoundError:
            self._log_threadsafe(f"inbox missing: {self._watch_dir}")

    def _clear_log(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    def _clear_history(self) -> None:
        self._history.clear()
        self._refresh_history()
        self._log_threadsafe("history cleared")

    def _refresh_history(self) -> None:
        if not hasattr(self, "_history_tree"):
            return
        self._render_history(self._history.recent())

    # ---- history row interactions ------------------------------------

    def _build_history_context_menu(self) -> None:
        menu = tk.Menu(
            self, tearoff=0, bg=COLOR_PANEL, fg=COLOR_TEXT,
            activebackground=COLOR_BTN_HOVER, activeforeground=COLOR_TEXT,
            bd=0,
        )
        menu.add_command(label="Reprint", command=self._reprint_selected)
        menu.add_command(label="Open file", command=self._open_selected_file)
        menu.add_command(label="Show in folder", command=self._show_selected_in_folder)
        menu.add_separator()
        menu.add_command(label="Filter to this submitter",
                         command=lambda: self._filter_to_field("submitter"))
        menu.add_command(label="Filter to this printer",
                         command=lambda: self._filter_to_field("printer"))
        menu.add_separator()
        menu.add_command(label="Copy filename", command=self._copy_selected_filename)
        self._history_menu = menu
        self._history_tree.bind("<Button-3>", self._on_history_right_click)
        self._history_tree.bind("<Double-Button-1>", lambda _e: self._open_selected_file())

    def _on_history_right_click(self, event) -> None:
        iid = self._history_tree.identify_row(event.y)
        if iid:
            self._history_tree.selection_set(iid)
            self._history_tree.focus(iid)
            try:
                self._history_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self._history_menu.grab_release()

    def _selected_history_record(self) -> PrintRecord | None:
        sel = self._history_tree.selection()
        if not sel:
            return None
        return getattr(self, "_history_row_records", {}).get(sel[0])

    def _find_printed_file(self, record: PrintRecord) -> Path | None:
        candidates: list[Path] = []
        if record.submitter:
            sub_dir = self._printed_dir / record.submitter
            if sub_dir.exists():
                candidates.extend(sub_dir.iterdir())
        if self._printed_dir.exists():
            candidates.extend(self._printed_dir.iterdir())
        suffix = Path(record.filename).suffix.lower()
        stem = Path(record.filename).stem.lower()
        matches: list[Path] = []
        for cand in candidates:
            if not cand.is_file():
                continue
            if cand.suffix.lower() != suffix:
                continue
            if cand.name == record.filename or cand.stem.lower().startswith(stem):
                matches.append(cand)
        if not matches:
            return None
        exact = [m for m in matches if m.name == record.filename]
        if exact:
            return exact[0]
        return max(matches, key=lambda p: p.stat().st_mtime)

    def _reprint_selected(self) -> None:
        record = self._selected_history_record()
        if record is None:
            return
        source = self._find_printed_file(record)
        if source is None:
            self._log_threadsafe(f"reprint: archived file not found for {record.filename}")
            return
        target_name = f"reprint-{int(time.time())}-{record.filename}"
        target = self._watch_dir / target_name
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            self._log_threadsafe(f"reprint failed: {exc}")
            return
        self._log_threadsafe(f"reprint queued from {record.time_short}: {record.filename}")

    def _open_selected_file(self) -> None:
        record = self._selected_history_record()
        if record is None:
            return
        source = self._find_printed_file(record)
        if source is None:
            self._log_threadsafe(f"file no longer available: {record.filename}")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(source))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(source)])
        except OSError as exc:
            self._log_threadsafe(f"open failed: {exc}")

    def _show_selected_in_folder(self) -> None:
        record = self._selected_history_record()
        if record is None:
            return
        source = self._find_printed_file(record)
        if source is None:
            self._log_threadsafe(f"file no longer available: {record.filename}")
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", str(source)])
            else:
                subprocess.Popen(["xdg-open", str(source.parent)])
        except OSError as exc:
            self._log_threadsafe(f"reveal failed: {exc}")

    def _filter_to_field(self, field: str) -> None:
        record = self._selected_history_record()
        if record is None:
            return
        value = getattr(record, field, "")
        if value:
            self._filter_var.set(str(value))

    def _copy_selected_filename(self) -> None:
        record = self._selected_history_record()
        if record is None:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(record.filename)
        except tk.TclError:
            self._log_threadsafe("clipboard unavailable")

    # ---- thread-safe UI updates --------------------------------------

    def _log_threadsafe(self, message: str) -> None:
        self.after(0, self._append_log, message)

    def _record_threadsafe(self, record: PrintRecord) -> None:
        self._history.append(record)
        self.after(0, self._refresh_history)

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_text.configure(state="normal")
        self._log_text.insert("end", f"[{timestamp}] {message}\n")
        line_count = int(self._log_text.index("end-1c").split(".")[0])
        if line_count > LOG_LINE_LIMIT:
            self._log_text.delete("1.0", f"{line_count - LOG_LINE_LIMIT}.0")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _stat_threadsafe(self, key: str, delta: int) -> None:
        self.after(0, self._bump_stat, key, delta)

    def _bump_stat(self, key: str, delta: int) -> None:
        self._stats[key] = max(0, self._stats[key] + delta)
        self._stat_labels[key].configure(text=str(self._stats[key]))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _configure_logging() -> Path | None:
    """Console + rotating file handler in %APPDATA%/PrintWatcher/logs/."""
    from logging.handlers import RotatingFileHandler

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    appdata = os.environ.get("APPDATA")
    log_dir = Path(appdata) / "PrintWatcher" / "logs" if appdata else Path.home() / ".printwatcher" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "printwatcher.log",
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
        return log_dir
    except OSError:
        return None


def _maybe_init_sentry() -> bool:
    """Init Sentry if SENTRY_DSN is set and the SDK is installed; opt-in."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk  # type: ignore[import-not-found]
    except ImportError:
        log.info("SENTRY_DSN set but sentry-sdk not installed; skipping")
        return False
    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.0,
        send_default_pii=False,
    )
    log.info("sentry initialised")
    return True


def main() -> None:
    log_dir = _configure_logging()
    if log_dir:
        log.info("logging to %s", log_dir)
    _maybe_init_sentry()
    watch_dir, sumatra = discover_paths()
    App(watch_dir=watch_dir, sumatra=sumatra).mainloop()


if __name__ == "__main__":
    main()
