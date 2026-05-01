"""PUT /api/options round-trip — verifies the wire format matches PrintOptions."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_options_get_default(client, auth_headers):
    r = await client.get("/api/options", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"printer": None, "copies": 1, "sides": None, "color": None}


@pytest.mark.asyncio
async def test_options_put_round_trip(client, auth_headers, watcher):
    payload = {"printer": "HP LaserJet", "copies": 5, "sides": "duplex", "color": "color"}
    r = await client.put("/api/options", headers=auth_headers, json=payload)
    assert r.status_code == 200
    assert r.json() == payload

    r = await client.get("/api/options", headers=auth_headers)
    assert r.json() == payload

    options = watcher.get_options()
    assert options.printer == "HP LaserJet"
    assert options.copies == 5
    assert options.sides == "duplex"
    assert options.color == "color"


@pytest.mark.asyncio
async def test_options_validates_copies_range(client, auth_headers):
    r = await client.put(
        "/api/options",
        headers=auth_headers,
        json={"copies": 200},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_options_validates_sides_enum(client, auth_headers):
    r = await client.put(
        "/api/options",
        headers=auth_headers,
        json={"sides": "sideways"},
    )
    assert r.status_code == 422
