import threading
import time
import subprocess
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
import pystray
from PIL import Image, ImageDraw

WATCH_DIR = Path(r"C:\Users\YOUR_USERNAME\OneDrive\PrintInbox")
SUMATRA = Path(r"C:\Tools\SumatraPDF\SumatraPDF.exe")
PRINTED_DIR = WATCH_DIR / "_printed"
EXTS = {".pdf", ".png", ".jpg", ".jpeg"}

PRINTED_DIR.mkdir(parents=True, exist_ok=True)

paused = threading.Event()


def wait_until_stable(path: Path, checks=3, interval=1.0):
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


def print_file(path: Path):
    if paused.is_set():
        print(f"[skip-paused] {path.name}")
        return
    if not wait_until_stable(path):
        return
    print(f"[print] {path.name}")
    subprocess.run(
        [str(SUMATRA), "-print-to-default", "-silent", "-exit-on-print", str(path)],
        check=False,
    )
    try:
        path.rename(PRINTED_DIR / path.name)
    except OSError as e:
        print(f"[warn] could not move {path.name}: {e}")


class Handler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() in EXTS and PRINTED_DIR not in p.parents:
            threading.Thread(target=print_file, args=(p,), daemon=True).start()


def make_icon(color):
    img = Image.new("RGB", (64, 64), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((8, 16, 56, 52), fill=color, outline="black", width=2)
    d.rectangle((16, 8, 48, 20), fill="white", outline="black", width=2)
    return img


def main():
    obs = Observer()
    obs.schedule(Handler(), str(WATCH_DIR), recursive=False)
    obs.start()
    print(f"Watching {WATCH_DIR}")

    def toggle_pause(icon, item):
        if paused.is_set():
            paused.clear()
            icon.icon = make_icon("green")
            icon.title = "PrintWatcher — Active"
        else:
            paused.set()
            icon.icon = make_icon("red")
            icon.title = "PrintWatcher — Paused"

    def open_folder(icon, item):
        subprocess.Popen(["explorer", str(WATCH_DIR)])

    def quit_app(icon, item):
        obs.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            lambda item: "Resume" if paused.is_set() else "Pause", toggle_pause
        ),
        pystray.MenuItem("Open Inbox Folder", open_folder),
        pystray.MenuItem("Quit", quit_app),
    )
    icon = pystray.Icon(
        "PrintWatcher", make_icon("green"), "PrintWatcher — Active", menu
    )
    icon.run()
    obs.join()


if __name__ == "__main__":
    main()
