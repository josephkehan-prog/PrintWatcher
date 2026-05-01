"""WebSocket auth + fan-out coverage using FastAPI's TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_websocket_auth_required(app):
    """Connecting without sending the auth frame closes the socket."""
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "auth", "token": "wrong"})
                # Expect a close frame; the receive will raise.
                ws.receive_json()


def test_websocket_hello_after_auth(app, token):
    """Sending the right token gets a hello frame."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert "version" in hello


def test_websocket_receives_published_event(app, token, event_bus):
    """Events published after subscription reach connected clients."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json()["type"] == "hello"

            event_bus.publish({"type": "stat", "key": "printed", "delta": 1, "value": 7})
            frame = ws.receive_json()
            assert frame == {"type": "stat", "key": "printed", "delta": 1, "value": 7}
