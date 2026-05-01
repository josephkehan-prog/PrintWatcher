"""Entry point for ``python -m printwatcher.server``.

Boots a ``WatcherCore``, generates (or accepts) a token, starts uvicorn on
127.0.0.1, and writes ``%LOCALAPPDATA%/PrintWatcher/server.json`` so the
WinUI shell can discover the port.
"""

from __future__ import annotations

import argparse
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
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(name)s: %(message)s")

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
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    finally:
        if discovery_path is not None and discovery_path.exists():
            try:
                discovery_path.unlink()
            except OSError:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
