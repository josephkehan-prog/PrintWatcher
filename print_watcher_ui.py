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

EXTS = frozenset({".pdf", ".png", ".jpg", ".jpeg"})
POLL_INTERVAL_SEC = 5.0
STABLE_CHECKS = 3
STABLE_INTERVAL_SEC = 1.0
LOG_LINE_LIMIT = 500
PRINTED_SUBDIR = "_printed"

DEFAULT_SUMATRA = Path(r"C:\Tools\SumatraPDF\SumatraPDF.exe")

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


def _local_user() -> str:
    return (
        os.environ.get("USERNAME")
        or os.environ.get("USER")
        or "local"
    )


def _submitter_for(path: Path, watch_dir: Path) -> str:
    """Multi-user attribution: subfolder name when present, else current OS user."""
    try:
        relative = path.relative_to(watch_dir)
    except ValueError:
        return _local_user()
    if len(relative.parts) <= 1:
        return _local_user()
    return relative.parts[0]


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

        options = self._options_provider()
        printer_label = options.printer or DEFAULT_PRINTER_LABEL
        details = [f"to {printer_label}"]
        if options.copies > 1:
            details.append(f"{options.copies} copies")
        if options.sides:
            details.append(_sides_label(options.sides))
        if options.color:
            details.append(_color_label(options.color))
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

# Palette: https://coolors.co/00a6fb-0582ca-006494
COLOR_BG = "#006494"          # deep teal-blue — base
COLOR_PANEL = "#0582ca"       # medium blue — cards lifted from base
COLOR_LOG_BG = "#003e5c"      # base deepened for log surface
COLOR_TEXT = "#e0f2ff"        # derived near-white with sky tint
COLOR_MUTED = "#a3c4d9"       # TEXT desaturated for secondary labels
COLOR_OK = "#00a6fb"          # brightest sky blue — active / running
COLOR_ERR = "#6b8a9c"         # derived slate — paused / idle (palette has no warm accent)
COLOR_LOG_TEXT = "#e0f2ff"    # match TEXT
COLOR_BTN_HOVER = "#0a96e0"   # between PANEL and OK for button hover


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

        self.title("PrintWatcher")
        self.geometry("960x680")
        self.minsize(720, 560)
        self.configure(bg=COLOR_BG)

        self._build_ui()
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
            self._history_tree.heading(col, text=label)
            anchor = "e" if col == "copies" else "w"
            self._history_tree.column(col, width=width, anchor=anchor, stretch=(col == "file"))
        self._history_tree.tag_configure("ok", foreground=COLOR_OK)
        self._history_tree.tag_configure("error", foreground=COLOR_ERR)
        self._history_tree.pack(side="left", fill="both", expand=True)
        tree_scroll = ttk.Scrollbar(tree_inner, orient="vertical", command=self._history_tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self._history_tree.configure(yscrollcommand=tree_scroll.set)

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
        self.destroy()

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
        for iid in self._history_tree.get_children():
            self._history_tree.delete(iid)
        for record in self._history.recent():
            status_glyph = "OK" if record.status == "ok" else "FAIL"
            tag = "ok" if record.status == "ok" else "error"
            self._history_tree.insert(
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

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    watch_dir, sumatra = discover_paths()
    App(watch_dir=watch_dir, sumatra=sumatra).mainloop()


if __name__ == "__main__":
    main()
