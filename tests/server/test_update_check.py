"""``GET /api/update-check`` — once-a-day GitHub Releases poll with a 24 h cache."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient

from printwatcher.core import APP_VERSION


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _fake_response(payload: dict):
    """Return a context-manager-compatible fake urlopen response."""

    class _Resp:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *_):
            return False

        def read(self_inner) -> bytes:
            return json.dumps(payload).encode("utf-8")

    return _Resp()


def test_update_available(app, token) -> None:
    payload = {
        "tag_name": "v9.99.0",
        "html_url": "https://github.com/josephkehan-prog/PrintWatcher/releases/tag/v9.99.0",
    }
    client = TestClient(app)
    with client, patch(
        "printwatcher.server.routes.state.urllib.request.urlopen",
        return_value=_fake_response(payload),
    ):
        r = client.get("/api/update-check", headers=_auth(token))
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["latest"] == "9.99.0"
    assert body["has_update"] is True
    assert body["html_url"].startswith("https://github.com/")


def test_no_update_when_versions_match(app, token) -> None:
    payload = {
        "tag_name": f"v{APP_VERSION}",
        "html_url": "https://github.com/example",
    }
    client = TestClient(app)
    with client, patch(
        "printwatcher.server.routes.state.urllib.request.urlopen",
        return_value=_fake_response(payload),
    ):
        r = client.get("/api/update-check", headers=_auth(token))
    body = r.json()
    assert body["latest"] == APP_VERSION
    assert body["has_update"] is False


def test_network_error_is_graceful(app, token) -> None:
    """A transient outage must not break the dashboard — return no-update."""
    import urllib.error
    client = TestClient(app)
    with client, patch(
        "printwatcher.server.routes.state.urllib.request.urlopen",
        side_effect=urllib.error.URLError("offline"),
    ):
        r = client.get("/api/update-check", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["has_update"] is False
    assert body["latest"] is None


def test_cache_hit_skips_network(app, token) -> None:
    """Second call within 24 h must not re-hit the network."""
    payload = {"tag_name": "v9.99.0", "html_url": "https://example/x"}
    client = TestClient(app)
    with client, patch(
        "printwatcher.server.routes.state.urllib.request.urlopen",
        return_value=_fake_response(payload),
    ) as mock:
        # first call populates cache
        client.get("/api/update-check", headers=_auth(token))
        # additional fakes for any future call would need a fresh _fake_response;
        # second call MUST be served from cache without invoking urlopen again.
        client.get("/api/update-check", headers=_auth(token))
        assert mock.call_count == 1


def test_force_refreshes_cache(app, token) -> None:
    payload = {"tag_name": "v1.0.0", "html_url": "https://example/x"}
    client = TestClient(app)
    with client, patch(
        "printwatcher.server.routes.state.urllib.request.urlopen",
        return_value=_fake_response(payload),
    ) as mock:
        client.get("/api/update-check", headers=_auth(token))
        client.get("/api/update-check?force=true", headers=_auth(token))
        assert mock.call_count == 2


def test_requires_token(app) -> None:
    client = TestClient(app)
    with client:
        r = client.get("/api/update-check")
    assert r.status_code == 401
