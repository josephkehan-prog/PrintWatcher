"""WebSocket fan-out endpoint.

First frame the client sends MUST be ``{"type":"auth","token":"..."}``.
Anything else closes the socket immediately. After auth the server sends a
``hello`` frame with the running version, then forwards every event the
``EventBus`` publishes.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from printwatcher.server.auth import constant_time_equals
from printwatcher.server.state import AppState

log = logging.getLogger("printwatcher.server.websocket")

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    state: AppState = ws.app.state.printwatcher
    await ws.accept()
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=5)
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
        await ws.close(code=4401)
        return

    token = first.get("token") if isinstance(first, dict) else None
    if not isinstance(token, str) or not constant_time_equals(token, state.token):
        await ws.close(code=4401)
        return

    queue = state.events.subscribe()
    try:
        await ws.send_json({
            "type": "hello",
            "version": state.app_version,
            "paused": state.watcher.is_paused,
        })
        while True:
            event = await queue.get()
            await ws.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - defensive
        log.exception("ws fan-out error")
        try:
            await ws.close(code=1011)
        except Exception:
            pass
    finally:
        state.events.unsubscribe(queue)
