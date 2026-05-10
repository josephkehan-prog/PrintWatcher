"""Entry point for ``python -m printwatcher.server``.

Boots a ``WatcherCore``, generates (or accepts) a token, starts uvicorn on
127.0.0.1, and writes ``%LOCALAPPDATA%/PrintWatcher/server.json`` so the
WinUI shell can discover the port.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import socket
import sys
from pathlib import Path

import uvicorn

from printwatcher.core import APP_VERSION, WatcherCore, discover_paths
from printwatcher.server.app import create_app
from printwatcher.server.auth import generate_token
from printwatcher.server.events import EventBus

log = logging.getLogger("printwatcher.server")


def _ensure_console_streams() -> Path | None:
    """When the backend runs as a PyInstaller --windowed exe, sys.stdout
    and sys.stderr are ``None``. uvicorn's ColourizedFormatter calls
    ``stream.isatty()`` in its ``__init__`` and crashes with
    ``AttributeError: 'NoneType' object has no attribute 'isatty'``.

    Redirect both to a rotating log file in %LOCALAPPDATA%/PrintWatcher/
    so we keep the diagnostic stream AND give uvicorn a real file handle
    with a working ``.isatty()`` (returns False, no colour codes).

    Returns the log file path if redirection happened, else None.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    log_dir = Path(base) / "PrintWatcher" if base else Path.home() / ".printwatcher"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "backend.log"
    # line-buffered text mode so a `tail -f` style reader sees output promptly.
    sink = log_path.open("a", buffering=1, encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = sink
    if sys.stderr is None:
        sys.stderr = sink
    return log_path


def _server_json_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / "PrintWatcher" / "server.json"
    return Path.home() / ".printwatcher" / "server.json"


def _pick_port(requested: int) -> int:
    if requested != 0:
        return requested
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _write_discovery(port: int, token: str) -> Path:
    target = _server_json_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "port": port,
                "pid": os.getpid(),
                "token": token,
                "version": APP_VERSION,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Restrict to owner read/write. On Windows, %LOCALAPPDATA% ACLs already
    # restrict to the user; chmod is a no-op on the FAT/NTFS POSIX layer.
    # On Linux/macOS dev fallback (~/.printwatcher/), the default umask
    # would otherwise leave the bearer token world-readable.
    with contextlib.suppress(OSError):
        target.chmod(0o600)
    return target


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="printwatcher.server")
    parser.add_argument("--port", type=int, default=0, help="loopback port (0 = ephemeral)")
    parser.add_argument(
        "--token",
        default=None,
        help="bearer token shared with the WinUI shell. Auto-generated if omitted.",
    )
    parser.add_argument(
        "--inbox",
        type=Path,
        default=None,
        help="watch directory override; defaults to discover_paths()",
    )
    parser.add_argument(
        "--sumatra",
        type=Path,
        default=None,
        help="path to SumatraPDF.exe; defaults to discover_paths()",
    )
    parser.add_argument(
        "--no-discovery",
        action="store_true",
        help="don't write the server.json discovery file (testing only)",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("debug", "info", "warning", "error"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    redirected_log = _ensure_console_streams()
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(name)s: %(message)s")
    if redirected_log is not None:
        log.info("stdout/stderr were None (windowed exe); redirected to %s", redirected_log)

    inbox, sumatra = discover_paths()
    if args.inbox is not None:
        inbox = args.inbox
    if args.sumatra is not None:
        sumatra = args.sumatra

    watcher = WatcherCore(watch_dir=inbox, sumatra=sumatra)
    events = EventBus()
    token = args.token or generate_token()
    port = _pick_port(args.port)

    app = create_app(watcher, events, token, app_version=APP_VERSION, auto_start=True)

    discovery_path: Path | None = None
    if not args.no_discovery:
        discovery_path = _write_discovery(port, token)
        log.info("wrote discovery file %s", discovery_path)

    log.info("PrintWatcher backend listening on 127.0.0.1:%s", port)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level=args.log_level,
        access_log=False,
        # Skip uvicorn's default ColourizedFormatter — it calls
        # stream.isatty() in __init__, which crashes when sys.stdout is
        # None (PyInstaller --windowed). Our basicConfig above is enough.
        log_config=None,
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    finally:
        if discovery_path is not None and discovery_path.exists():
            with contextlib.suppress(OSError):
                discovery_path.unlink()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
