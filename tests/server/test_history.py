"""History query + filter coverage."""

from __future__ import annotations

import pytest

from printwatcher.core import PrintRecord


@pytest.fixture
def seeded_history(watcher):
    records = [
        PrintRecord(timestamp="2026-04-29T10:00:00", filename="quiz.pdf", status="ok",
                    submitter="MaryDoe", copies=2),
        PrintRecord(timestamp="2026-04-29T10:05:00", filename="exam.pdf", status="error",
                    submitter="JoeRoe", detail="sumatra exit=1"),
        PrintRecord(timestamp="2026-04-29T10:10:00", filename="report.png", status="ok",
                    submitter="MaryDoe"),
    ]
    for r in records:
        watcher.history.append(r)
    return records


@pytest.mark.asyncio
async def test_history_returns_recent(client, auth_headers, seeded_history):
    r = await client.get("/api/history", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3
    # recent() reverses, so most recent first
    assert rows[0]["filename"] == "report.png"


@pytest.mark.asyncio
async def test_history_substring_filter(client, auth_headers, seeded_history):
    r = await client.get("/api/history?q=quiz", headers=auth_headers)
    rows = r.json()
    assert [row["filename"] for row in rows] == ["quiz.pdf"]


@pytest.mark.asyncio
async def test_history_submitter_filter(client, auth_headers, seeded_history):
    r = await client.get("/api/history?q=MaryDoe", headers=auth_headers)
    assert {row["filename"] for row in r.json()} == {"quiz.pdf", "report.png"}


@pytest.mark.asyncio
async def test_history_regex_filter(client, auth_headers, seeded_history):
    r = await client.get("/api/history?regex=%5Eq", headers=auth_headers)  # %5E = ^
    rows = r.json()
    assert [row["filename"] for row in rows] == ["quiz.pdf"]


@pytest.mark.asyncio
async def test_history_invalid_regex(client, auth_headers):
    r = await client.get("/api/history?regex=%5B", headers=auth_headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_history_clear(client, auth_headers, watcher, seeded_history):
    r = await client.delete("/api/history", headers=auth_headers)
    assert r.status_code == 204
    assert watcher.history.recent() == []
