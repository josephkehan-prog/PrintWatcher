"""``POST /api/shutdown`` — graceful exit triggered by the WinUI tray Quit menu."""

from __future__ import annotations

import os
import signal
import threading

from fastapi import APIRouter, Depends

from printwatcher.server.auth import require_token
from printwatcher.server.state import AppState, get_state

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


def _delayed_signal() -> None:
    # Give the HTTP response time to flush before tearing down uvicorn.
    threading.Timer(0.1, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()


@router.post("/shutdown")
def shutdown(state: AppState = Depends(get_state)) -> dict[str, str]:
    state.events.publish({"type": "shutdown"})
    state.watcher.stop()
    _delayed_signal()
    return {"status": "shutting down"}
