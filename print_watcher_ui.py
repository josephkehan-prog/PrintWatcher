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

import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass, replace
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
        printed_dir: Path,
        log_cb: Callable[[str], None],
        stat_cb: Callable[[str, int], None],
        options_provider: Callable[[], PrintOptions],
    ) -> None:
        super().__init__(daemon=True, name="PrinterWorker")
        self._sumatra = sumatra
        self._printed_dir = printed_dir
        self._log = log_cb
        self._stat = stat_cb
        self._options_provider = options_provider
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
            return

        options = self._options_provider()
        printer_label = options.printer or DEFAULT_PRINTER_LABEL
        details = [f"to {printer_label}"]
        if options.copies > 1:
            details.append(f"{options.copies} copies")
        if options.sides:
            details.append(options.sides)
        if options.color:
            details.append(options.color)
        self._log(f"printing: {path.name} ({', '.join(details)})")

        try:
            result = subprocess.run(
                options.to_sumatra_args(self._sumatra, path),
                check=False,
            )
        except FileNotFoundError:
            self._log(f"SumatraPDF not found at {self._sumatra}")
            self._stat("errors", 1)
            return
        except OSError as exc:
            self._log(f"launch failed for {path.name}: {exc}")
            self._stat("errors", 1)
            return

        if result.returncode != 0:
            self._log(f"sumatra exit={result.returncode}: {path.name}")
            self._stat("errors", 1)
            return

        try:
            target = _unique_target(self._printed_dir, path.name)
            path.rename(target)
            self._log(f"done: {path.name}")
            self._stat("printed", 1)
        except OSError as exc:
            self._log(f"move failed for {path.name}: {exc}")
            self._stat("errors", 1)


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
        if path.parent != self._watch_dir:
            return
        if self._printed_dir in path.parents:
            return
        if not path.is_file():
            return
        self._worker.submit(path)


def _poll_inbox(watch_dir: Path, worker: PrinterWorker, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            for entry in watch_dir.iterdir():
                if entry.is_file() and entry.suffix.lower() in EXTS:
                    worker.submit(entry)
        except FileNotFoundError:
            pass
        stop.wait(POLL_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

# Palette: https://coolors.co/f5fbef-2e294e-129490-9a879d-7a3b69
COLOR_BG = "#2e294e"          # base — dark indigo
COLOR_PANEL = "#3a345e"       # base lifted ~5% lightness for cards
COLOR_LOG_BG = "#1f1c36"      # base deepened for log surface
COLOR_TEXT = "#f5fbef"        # off-white
COLOR_MUTED = "#9a879d"       # muted mauve
COLOR_OK = "#129490"          # teal — active / success
COLOR_ERR = "#7a3b69"         # wine — paused / errors
COLOR_LOG_TEXT = "#d4cdd6"    # softened off-white with palette undertone
COLOR_BTN_HOVER = "#4a4470"   # base lifted further for button hover


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
        self._options = PrintOptions()

        self.title("PrintWatcher")
        self.geometry("820x620")
        self.minsize(660, 520)
        self.configure(bg=COLOR_BG)

        self._build_ui()

        self._worker = PrinterWorker(
            sumatra=sumatra,
            printed_dir=self._printed_dir,
            log_cb=self._log_threadsafe,
            stat_cb=self._stat_threadsafe,
            options_provider=lambda: self._options,
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
            padding=(12, 6),
        )
        style.map(
            "Action.TButton",
            background=[("active", COLOR_BTN_HOVER)],
            foreground=[("active", COLOR_TEXT)],
        )

        header = tk.Frame(self, bg=COLOR_BG, padx=18, pady=14)
        header.pack(fill="x")

        self._dot = tk.Canvas(
            header, width=14, height=14, bg=COLOR_BG, highlightthickness=0
        )
        self._dot.pack(side="left")
        self._set_dot(COLOR_OK)

        self._status_label = tk.Label(
            header,
            text="Active",
            fg=COLOR_TEXT,
            bg=COLOR_BG,
            font=("Segoe UI", 13, "bold"),
            padx=10,
        )
        self._status_label.pack(side="left")

        tk.Label(
            header,
            text=str(self._watch_dir),
            fg=COLOR_MUTED,
            bg=COLOR_BG,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(8, 0))

        stats = tk.Frame(self, bg=COLOR_BG, padx=18)
        stats.pack(fill="x")
        self._stat_labels: dict[str, tk.Label] = {}
        for key, title in (
            ("printed", "Printed"),
            ("pending", "In queue"),
            ("errors", "Errors"),
        ):
            cell = tk.Frame(stats, bg=COLOR_PANEL, padx=16, pady=10)
            cell.pack(side="left", padx=(0, 10), pady=(0, 8))
            tk.Label(
                cell, text=title, fg=COLOR_MUTED, bg=COLOR_PANEL,
                font=("Segoe UI", 9),
            ).pack(anchor="w")
            value = tk.Label(
                cell, text="0", fg=COLOR_TEXT, bg=COLOR_PANEL,
                font=("Segoe UI", 18, "bold"),
            )
            value.pack(anchor="w")
            self._stat_labels[key] = value

        self._build_options_panel()

        log_wrap = tk.Frame(self, bg=COLOR_BG, padx=18, pady=8)
        log_wrap.pack(fill="both", expand=True)
        self._log_text = tk.Text(
            log_wrap,
            bg=COLOR_LOG_BG,
            fg=COLOR_LOG_TEXT,
            insertbackground=COLOR_LOG_TEXT,
            font=("Consolas", 10),
            wrap="none",
            relief="flat",
            padx=10,
            pady=8,
        )
        self._log_text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(
            log_wrap, orient="vertical", command=self._log_text.yview
        )
        scroll.pack(side="right", fill="y")
        self._log_text.configure(yscrollcommand=scroll.set, state="disabled")

        bar = tk.Frame(self, bg=COLOR_BG, padx=18, pady=14)
        bar.pack(fill="x")
        self._pause_btn = ttk.Button(
            bar, text="Pause", style="Action.TButton", command=self._toggle_pause
        )
        self._pause_btn.pack(side="left")
        ttk.Button(
            bar, text="Open inbox", style="Action.TButton",
            command=lambda: self._open_folder(self._watch_dir),
        ).pack(side="left", padx=8)
        ttk.Button(
            bar, text="Open printed", style="Action.TButton",
            command=lambda: self._open_folder(self._printed_dir),
        ).pack(side="left", padx=8)
        ttk.Button(
            bar, text="Rescan now", style="Action.TButton",
            command=self._rescan_now,
        ).pack(side="left", padx=8)
        ttk.Button(
            bar, text="Clear log", style="Action.TButton",
            command=self._clear_log,
        ).pack(side="left", padx=8)
        ttk.Button(
            bar, text="Quit", style="Action.TButton", command=self._on_close
        ).pack(side="right")

    def _set_dot(self, color: str) -> None:
        self._dot.delete("all")
        self._dot.create_oval(2, 2, 13, 13, fill=color, outline="")

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
            self._options = replace(self._options, printer=None)
        self._log_threadsafe(f"printer list refreshed ({len(names)} found)")

    def _on_printer_change(self, _event: object = None) -> None:
        choice = self._printer_var.get()
        printer = None if choice == DEFAULT_PRINTER_LABEL else choice
        self._options = replace(self._options, printer=printer)
        self._log_threadsafe(f"printer set: {choice}")

    def _on_copies_change(self) -> None:
        try:
            value = int(self._copies_var.get())
        except (tk.TclError, ValueError):
            value = 1
        value = max(1, min(99, value))
        self._copies_var.set(value)
        self._options = replace(self._options, copies=value)
        self._log_threadsafe(f"copies set: {value}")

    def _on_sides_change(self, _event: object = None) -> None:
        label = self._sides_var.get()
        value = next((v for lab, v in SIDES_CHOICES if lab == label), None)
        self._options = replace(self._options, sides=value)
        self._log_threadsafe(f"sides set: {label}")

    def _on_color_change(self, _event: object = None) -> None:
        label = self._color_var.get()
        value = next((v for lab, v in COLOR_CHOICES if lab == label), None)
        self._options = replace(self._options, color=value)
        self._log_threadsafe(f"color set: {label}")

    # ---- watcher lifecycle -------------------------------------------

    def _start_observer(self) -> None:
        observer = Observer()
        handler = InboxHandler(self._watch_dir, self._printed_dir, self._worker)
        observer.schedule(handler, str(self._watch_dir), recursive=False)
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
            self._status_label.configure(text="Active")
            self._set_dot(COLOR_OK)
            self._pause_btn.configure(text="Pause")
            self._log_threadsafe("resumed")
        else:
            self._worker.paused.set()
            self._status_label.configure(text="Paused")
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

    # ---- thread-safe UI updates --------------------------------------

    def _log_threadsafe(self, message: str) -> None:
        self.after(0, self._append_log, message)

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
