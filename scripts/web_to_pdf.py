"""Render a URL to PDF via local headless Chromium/Edge, then drop in PrintInbox.

Usage:
    python scripts/web_to_pdf.py https://example.com
    python scripts/web_to_pdf.py https://example.com --out report.pdf
    python scripts/web_to_pdf.py https://example.com --landscape --no-print

Tries (in order): msedge.exe, chrome.exe, chromium.exe — whichever is first
on PATH or in standard install locations. Uses --headless --print-to-pdf,
which is built into recent Edge / Chrome and produces a PDF without
needing any pip dependencies.

`--no-print` writes the PDF next to your current working dir instead of the
PrintInbox.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("printwatcher.web2pdf")

CHROMIUM_NAMES = ("msedge", "chrome", "chromium")
WINDOWS_INSTALL_HINTS = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)


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


def find_browser() -> Path | None:
    for name in CHROMIUM_NAMES:
        located = shutil.which(name)
        if located:
            return Path(located)
    for hint in WINDOWS_INSTALL_HINTS:
        if hint.exists():
            return hint
    return None


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def slug_from_url(url: str) -> str:
    cleaned = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
    cleaned = _SAFE.sub("_", cleaned)
    cleaned = cleaned.strip("._")
    return cleaned[:80] or "page"


def render(browser: Path, url: str, output: Path, landscape: bool) -> bool:
    output.parent.mkdir(parents=True, exist_ok=True)
    args = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={output}",
    ]
    if landscape:
        args.append("--landscape")
    args.append(url)
    log.info("rendering %s -> %s", url, output.name)
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.error("browser launch failed: %s", exc)
        return False
    if result.returncode != 0:
        log.error("browser exited %s; stderr=%s", result.returncode, result.stderr.strip())
        return False
    if not output.exists() or output.stat().st_size == 0:
        log.error("browser produced no output")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="URL to render")
    parser.add_argument("--out", type=Path, default=None,
                        help="output filename (default: derived from URL)")
    parser.add_argument("--landscape", action="store_true", help="landscape orientation")
    parser.add_argument("--no-print", action="store_true",
                        help="write next to current dir instead of PrintInbox")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    browser = find_browser()
    if browser is None:
        log.error("no msedge/chrome/chromium found on PATH or standard locations")
        return 2

    target_dir = Path.cwd() if args.no_print else discover_inbox()
    filename = args.out or Path(f"{slug_from_url(args.url)}-{int(time.time())}.pdf")
    output = target_dir / filename if not filename.is_absolute() else filename

    if not render(browser, args.url, output, args.landscape):
        return 1

    log.info("wrote %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
