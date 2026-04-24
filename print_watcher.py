import time
import subprocess
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

WATCH_DIR = Path(r"C:\Users\YOUR_USERNAME\OneDrive\PrintInbox")
SUMATRA = Path(r"C:\Tools\SumatraPDF\SumatraPDF.exe")
PRINTED_DIR = WATCH_DIR / "_printed"
EXTS = {".pdf", ".png", ".jpg", ".jpeg"}

PRINTED_DIR.mkdir(parents=True, exist_ok=True)


def wait_until_stable(path: Path, checks=3, interval=1.0):
    """OneDrive writes in chunks; wait until size stops changing."""
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
            print_file(p)


if __name__ == "__main__":
    obs = Observer()
    obs.schedule(Handler(), str(WATCH_DIR), recursive=False)
    obs.start()
    print(f"Watching {WATCH_DIR}")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()
