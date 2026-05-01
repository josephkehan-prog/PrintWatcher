"""``GET /api/state`` snapshot shape + ``POST /api/pause`` round-trip."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_state_snapshot_shape(client, auth_headers):
    r = await client.get("/api/state", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()

    assert "version" in body
    assert set(body["stats"].keys()) == {"printed", "today", "pending", "errors"}
    assert body["paused"] is False
    assert "options" in body
    assert "preferences" in body
    assert "printers" in body
    assert "pending" in body and isinstance(body["pending"], list)


@pytest.mark.asyncio
async def test_pause_round_trip(client, auth_headers, watcher):
    r = await client.post("/api/pause", headers=auth_headers, json={"paused": True})
    assert r.status_code == 200
    assert r.json() == {"paused": True}
    assert watcher.is_paused is True

    r = await client.post("/api/pause", headers=auth_headers, json={"paused": False})
    assert r.json() == {"paused": False}
    assert watcher.is_paused is False


@pytest.mark.asyncio
async def test_version_endpoint(client, auth_headers):
    r = await client.get("/api/version", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "app" in body and "python" in body
