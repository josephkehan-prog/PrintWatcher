"""Minimal system-tray watcher.

Edit ``WATCH_DIR`` and ``SUMATRA`` below to point at your inbox folder and
SumatraPDF executable. ``printwatcher.core.discover_paths()`` reads those
constants from this file to keep both entrypoints in sync.
"""

import logging
import subprocess
import threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageOps
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from printwatcher.core import EXTS, PRINTED_SUBDIR

WATCH_DIR = Path(r"C:\Users\YOUR_USERNAME\OneDrive\PrintInbox")
SUMATRA = Path(r"C:\Tools\SumatraPDF\SumatraPDF.exe")
PRINTED_DIR = WATCH_DIR / PRINTED_SUBDIR

PRINTED_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [tray] %(message)s")
log = logging.getLogger("printwatcher.tray")

paused = threading.Event()

_STABLE_CHECKS = 3
_STABLE_INTERVAL_SEC = 1.0
_ASSET_ICON = Path(__file__).parent / "assets" / "printwatcher.png"


def wait_until_stable(
    path: Path,
    checks: int = _STABLE_CHECKS,
    interval: float = _STABLE_INTERVAL_SEC,
) -> bool:
    """Poll until file size has not changed for ``checks`` consecutive samples."""
    import time

    last = -1
    stable = 0
    while stable < checks:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False
        if size == last and size > 0:
            stable += 1
        else:
            stable = 0
            last = size
        time.sleep(interval)
    return True


def print_file(path: Path) -> None:
    if paused.is_set():
        log.info("skip-paused: %s", path.name)
        return
    if not wait_until_stable(path):
        return
    log.info("print: %s", path.name)
    subprocess.run(
        [str(SUMATRA), "-print-to-default", "-silent", "-exit-on-print", str(path)],
        check=False,
    )
    try:
        path.rename(PRINTED_DIR / path.name)
    except OSError as exc:
        log.warning("could not move %s: %s", path.name, exc)


class Handler(FileSystemEventHandler):
    def on_created(self, event) -> None:
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() in EXTS and PRINTED_DIR not in p.parents:
            threading.Thread(target=print_file, args=(p,), daemon=True).start()


def _load_icon(active: bool) -> Image.Image:
    """Return the tray icon, tinted muted/red when paused."""
    try:
        img = Image.open(_ASSET_ICON).convert("RGBA")
    except (FileNotFoundError, OSError):
        return _fallback_icon(active)
    if active:
        return img
    # Desaturate + slight red shift to signal paused.
    grey = ImageOps.grayscale(img).convert("RGBA")
    grey.putalpha(img.split()[-1])
    return grey


def _fallback_icon(active: bool) -> Image.Image:
    """Procedural fallback if the bundled PNG is missing."""
    img = Image.new("RGB", (64, 64), "white")
    d = ImageDraw.Draw(img)
    color = "#1F8A3F" if active else "#A33"
    d.rectangle((8, 16, 56, 52), fill=color, outline="black", width=2)
    d.rectangle((16, 8, 48, 20), fill="white", outline="black", width=2)
    return img


def main() -> None:
    obs = Observer()
    obs.schedule(Handler(), str(WATCH_DIR), recursive=False)
    obs.start()
    log.info("watching %s", WATCH_DIR)

    def toggle_pause(icon, _item) -> None:
        if paused.is_set():
            paused.clear()
            icon.icon = _load_icon(active=True)
            icon.title = "PrintWatcher — Active"
        else:
            paused.set()
            icon.icon = _load_icon(active=False)
            icon.title = "PrintWatcher — Paused"

    def open_folder(_icon, _item) -> None:
        subprocess.Popen(["explorer", str(WATCH_DIR)])

    def quit_app(icon, _item) -> None:
        obs.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            lambda _item: "Resume" if paused.is_set() else "Pause", toggle_pause
        ),
        pystray.MenuItem("Open Inbox Folder", open_folder),
        pystray.MenuItem("Quit", quit_app),
    )
    icon = pystray.Icon(
        "PrintWatcher", _load_icon(active=True), "PrintWatcher — Active", menu
    )
    icon.run()
    obs.join()


if __name__ == "__main__":
    main()
