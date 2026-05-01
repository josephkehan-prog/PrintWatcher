"""Bearer-token enforcement on every REST route."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_state_requires_token(client):
    r = await client.get("/api/state")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_state_rejects_wrong_token(client):
    r = await client.get("/api/state", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_state_accepts_correct_token(client, auth_headers):
    r = await client.get("/api/state", headers=auth_headers)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_options_route_protected(client):
    r = await client.put("/api/options", json={"copies": 2})
    assert r.status_code == 401
