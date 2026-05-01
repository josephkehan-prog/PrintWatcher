"""Tool runner streams stdout + log frames and reports an exit code."""

from __future__ import annotations

import asyncio
import sys
import time
import types

import pytest


@pytest.fixture
def fake_tool(monkeypatch):
    """Register an in-memory ``scripts._fake_tool`` exposing ``main(argv)``."""
    module = types.ModuleType("scripts._fake_tool")

    def main(argv: list[str]) -> int:
        print("hello stdout")
        import logging
        logging.getLogger("fake_tool").info("hello logging")
        return 0 if argv == ["ok"] else 1

    module.main = main
    monkeypatch.setitem(sys.modules, "scripts._fake_tool", module)
    return module


@pytest.mark.asyncio
async def test_tool_run_disallowed_module(client, auth_headers):
    r = await client.post(
        "/api/tools/run",
        headers=auth_headers,
        json={"module": "os.system", "args": []},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_tool_run_starts(client, auth_headers, fake_tool, event_bus):
    r = await client.post(
        "/api/tools/run",
        headers=auth_headers,
        json={"module": "scripts._fake_tool", "args": ["ok"], "label": "fake"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    assert body["label"] == "fake"


@pytest.mark.asyncio
async def test_tool_emits_end_frame(client, auth_headers, fake_tool, event_bus):
    queue = event_bus.subscribe()
    r = await client.post(
        "/api/tools/run",
        headers=auth_headers,
        json={"module": "scripts._fake_tool", "args": ["ok"]},
    )
    assert r.status_code == 200

    # Drain frames up to the matching `end` event with a timeout.
    end_frame = None
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        if event.get("type") == "tool" and event.get("stream") == "end":
            end_frame = event
            break
    assert end_frame is not None, "tool runner never emitted an end frame"
    assert end_frame["rc"] == 0
