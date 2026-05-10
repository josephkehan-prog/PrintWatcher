"""``GET /api/inbox/health`` — disk usage + file counts for the inbox."""

from __future__ import annotations

from fastapi.testclient import TestClient

from printwatcher.core import PRINTED_SUBDIR, SCHEDULED_SUBDIR, SKIPPED_SUBDIR


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_inbox_health_empty(app, watcher, token, tmp_inbox) -> None:
    client = TestClient(app)
    with client:
        r = client.get("/api/inbox/health", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["watch_dir"] == str(tmp_inbox)
    assert body["inbox_count"] == 0
    assert body["printed_count"] == 0
    assert body["total_bytes"] == 0


def test_inbox_health_counts_each_bucket(app, watcher, token, tmp_inbox) -> None:
    # 2 inbox files, 3 printed, 1 skipped, all with known sizes.
    (tmp_inbox / "a.pdf").write_bytes(b"x" * 100)
    (tmp_inbox / "b.pdf").write_bytes(b"y" * 200)

    printed = tmp_inbox / PRINTED_SUBDIR
    printed.mkdir(exist_ok=True)
    (printed / "old1.pdf").write_bytes(b"z" * 50)
    sub = printed / "alice"
    sub.mkdir()
    (sub / "old2.pdf").write_bytes(b"w" * 75)
    (sub / "old3.pdf").write_bytes(b"v" * 25)

    skipped = tmp_inbox / SKIPPED_SUBDIR
    skipped.mkdir(exist_ok=True)
    (skipped / "broken.pdf").write_bytes(b"u" * 10)

    watcher._invalidate_inbox_health()
    client = TestClient(app)
    with client:
        r = client.get("/api/inbox/health", headers=_auth(token))

    body = r.json()
    assert body["inbox_count"] == 2
    assert body["inbox_bytes"] == 300
    assert body["printed_count"] == 3
    assert body["printed_bytes"] == 150
    assert body["skipped_count"] == 1
    assert body["skipped_bytes"] == 10
    assert body["total_bytes"] == 460


def test_inbox_health_uses_cache(app, watcher, token, tmp_inbox) -> None:
    """Within the TTL, a second poll must not re-walk the disk."""
    (tmp_inbox / "first.pdf").write_bytes(b"abc")
    watcher._invalidate_inbox_health()

    client = TestClient(app)
    with client:
        first = client.get("/api/inbox/health", headers=_auth(token)).json()
        # Add a file after the cache is warm; cached snapshot must not see it.
        (tmp_inbox / "second.pdf").write_bytes(b"abc")
        second = client.get("/api/inbox/health", headers=_auth(token)).json()

    assert first["inbox_count"] == 1
    assert second["inbox_count"] == 1, "second call must come from the cache"


def test_inbox_health_requires_token(app) -> None:
    client = TestClient(app)
    with client:
        r = client.get("/api/inbox/health")
    assert r.status_code == 401
