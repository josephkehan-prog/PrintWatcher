"""Tool runner — runs ``scripts.<module>.main(argv)`` in a thread pool.

Mirrors the legacy ``_run_tool_async`` helper from the Tk UI. Captures
``stdout``/``stderr`` line-by-line and routes stdlib ``logging`` records via a
dedicated handler. Both streams reach the WinUI shell as ``{type:"tool"}``
WebSocket frames.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import logging
import secrets
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from printwatcher.server.events import EventBus

log = logging.getLogger("printwatcher.server.tools")


class _LineSplitter(io.TextIOBase):
    """File-like object that emits one event per ``\\n``-terminated line."""

    def __init__(self, emit) -> None:
        self._emit = emit
        self._buffer = ""

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buffer += s
        while "\n" in self._buffer:
            line, _, self._buffer = self._buffer.partition("\n")
            if line:
                self._emit(line)
        return len(s)

    def flush(self) -> None:
        if self._buffer:
            self._emit(self._buffer)
            self._buffer = ""


class _LogBridge(logging.Handler):
    def __init__(self, emit) -> None:
        super().__init__()
        self._emit = emit

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._emit(record.levelname.lower(), self.format(record))
        except Exception:  # pragma: no cover - last-resort handler safety
            self.handleError(record)


class ToolRunner:
    """Thread pool that streams tool output through the EventBus."""

    def __init__(self, events: "EventBus", max_workers: int = 4) -> None:
        self._events = events
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pwtool")
        self._cancels: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def submit(
        self,
        module_name: str,
        argv: Iterable[str],
        label: str,
    ) -> tuple[str, Future[int]]:
        run_id = secrets.token_hex(8)
        cancel_flag = threading.Event()
        with self._lock:
            self._cancels[run_id] = cancel_flag
        future = self._pool.submit(self._run, run_id, module_name, list(argv), label, cancel_flag)
        future.add_done_callback(lambda _f: self._cancels.pop(run_id, None))
        return run_id, future

    def cancel(self, run_id: str) -> bool:
        flag = self._cancels.get(run_id)
        if flag is None:
            return False
        flag.set()
        return True

    def _run(
        self,
        run_id: str,
        module_name: str,
        argv: list[str],
        label: str,
        cancel: threading.Event,
    ) -> int:
        emit_stdout = lambda line: self._events.publish({
            "type": "tool", "run_id": run_id, "stream": "stdout", "line": line,
        })
        emit_log = lambda level, line: self._events.publish({
            "type": "tool", "run_id": run_id, "stream": "log",
            "level": level, "line": line,
        })

        bridge = _LogBridge(emit_log)
        bridge.setLevel(logging.INFO)
        bridge.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        root = logging.getLogger()
        root.addHandler(bridge)

        out_buf = _LineSplitter(emit_stdout)
        err_buf = _LineSplitter(lambda line: emit_log("error", line))

        rc = 1
        try:
            self._events.publish({
                "type": "tool", "run_id": run_id, "stream": "start",
                "label": label, "module": module_name,
            })
            try:
                module = importlib.import_module(module_name)
            except ImportError as exc:
                emit_log("error", f"could not import {module_name}: {exc}")
                return 2
            if not hasattr(module, "main"):
                emit_log("error", f"{module_name} has no main()")
                return 2

            with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
                try:
                    rc = int(module.main(argv) or 0)
                except SystemExit as exc:
                    rc = int(exc.code or 0)
                except Exception as exc:
                    log.exception("tool %s crashed", module_name)
                    emit_log("error", f"{type(exc).__name__}: {exc}")
                    rc = 1
            out_buf.flush()
            err_buf.flush()
            return rc
        finally:
            root.removeHandler(bridge)
            self._events.publish({
                "type": "tool", "run_id": run_id, "stream": "end",
                "rc": rc, "cancelled": cancel.is_set(),
            })
