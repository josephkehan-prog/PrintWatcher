"""Poll an IMAP mailbox folder for unread messages and save PDF attachments to PrintInbox.

Email yourself a PDF, label it "Print" (or whatever IMAP folder you choose),
and it'll auto-print when this poller runs.

Configuration (env vars or .env file):

    IMAP_HOST=imap.gmail.com
    IMAP_PORT=993
    IMAP_USER=you@example.com
    IMAP_PASSWORD=app-password-here
    IMAP_FOLDER=Print
    POLL_INTERVAL_SEC=60

Gmail and Microsoft 365 require an *app password* — not your regular login.
Generate one in your account security settings.

Run:
    python scripts/email_to_inbox.py

The script marks processed messages as Seen and never deletes them. Restart-safe.
Uses stdlib only (imaplib + email).
"""

from __future__ import annotations

import argparse
import email
import imaplib
import logging
import os
import re
import sys
import time
from email.message import Message
from pathlib import Path

DEFAULT_FOLDER = "Print"
DEFAULT_POLL_SEC = 60
DEFAULT_PORT = 993
ALLOWED_EXTS = frozenset({".pdf", ".png", ".jpg", ".jpeg"})

log = logging.getLogger("printwatcher.email")


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


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str, fallback: str) -> str:
    cleaned = _SAFE.sub("_", name.strip())
    cleaned = cleaned.strip("._")
    return cleaned or fallback


def extract_attachments(message: Message) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        disposition = (part.get("Content-Disposition") or "").lower()
        if "attachment" not in disposition and "inline" not in disposition:
            continue
        filename = part.get_filename()
        if not filename:
            continue
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_EXTS:
            continue
        try:
            payload = part.get_payload(decode=True)
        except Exception:  # pragma: no cover - malformed MIME
            continue
        if not payload:
            continue
        out.append((filename, payload))
    return out


def save_attachment(inbox: Path, filename: str, payload: bytes) -> Path:
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / safe_filename(filename, fallback=f"email-{int(time.time())}.pdf")
    if target.exists():
        target = target.with_name(f"{target.stem}-{int(time.time())}{target.suffix}")
    target.write_bytes(payload)
    return target


def process_unseen(client: imaplib.IMAP4_SSL, folder: str, inbox: Path) -> int:
    status, _ = client.select(folder)
    if status != "OK":
        log.error("could not select folder %r", folder)
        return 0
    status, response = client.search(None, "UNSEEN")
    if status != "OK":
        return 0
    saved = 0
    ids = response[0].split() if response and response[0] else []
    for msg_id in ids:
        status, data = client.fetch(msg_id, "(RFC822)")
        if status != "OK" or not data or not data[0]:
            continue
        raw = data[0][1]
        if not isinstance(raw, (bytes, bytearray)):
            continue
        message = email.message_from_bytes(raw)
        attachments = extract_attachments(message)
        if not attachments:
            continue
        for filename, payload in attachments:
            target = save_attachment(inbox, filename, payload)
            saved += 1
            log.info("saved %s (%d bytes) -> %s", filename, len(payload), target)
        client.store(msg_id, "+FLAGS", "\\Seen")
    return saved


def poll_loop(host: str, port: int, user: str, password: str,
              folder: str, inbox: Path, interval: float) -> None:
    log.info("polling %s@%s:%s folder=%r every %ss -> %s",
             user, host, port, folder, interval, inbox)
    while True:
        try:
            with imaplib.IMAP4_SSL(host, port) as client:
                client.login(user, password)
                count = process_unseen(client, folder, inbox)
                if count:
                    log.info("saved %d attachment(s) this cycle", count)
        except (imaplib.IMAP4.error, OSError) as exc:
            log.warning("imap cycle failed: %s", exc)
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="run a single fetch cycle and exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    host = os.environ.get("IMAP_HOST")
    user = os.environ.get("IMAP_USER")
    password = os.environ.get("IMAP_PASSWORD")
    if not (host and user and password):
        log.error("IMAP_HOST / IMAP_USER / IMAP_PASSWORD must be set")
        return 2
    port = int(os.environ.get("IMAP_PORT", str(DEFAULT_PORT)))
    folder = os.environ.get("IMAP_FOLDER", DEFAULT_FOLDER)
    interval = float(os.environ.get("POLL_INTERVAL_SEC", str(DEFAULT_POLL_SEC)))
    inbox = discover_inbox()

    if args.once:
        try:
            with imaplib.IMAP4_SSL(host, port) as client:
                client.login(user, password)
                count = process_unseen(client, folder, inbox)
            log.info("saved %d attachment(s)", count)
        except (imaplib.IMAP4.error, OSError) as exc:
            log.error("imap failed: %s", exc)
            return 1
        return 0

    try:
        poll_loop(host, port, user, password, folder, inbox, interval)
    except KeyboardInterrupt:
        log.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
