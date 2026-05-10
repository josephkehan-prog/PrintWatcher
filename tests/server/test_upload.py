"""``POST /api/inbox/drop`` upload route — sanitization and size cap."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_upload_accepts_pdf(app, token, tmp_inbox) -> None:
    client = TestClient(app)
    with client:
        r = client.post(
            "/api/inbox/drop",
            headers=_auth(token),
            files={"file": ("hello.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert r.status_code == 200, r.text
    assert (tmp_inbox / "hello.pdf").exists()


def test_upload_rejects_unsupported_extension(app, token) -> None:
    client = TestClient(app)
    with client:
        r = client.post(
            "/api/inbox/drop",
            headers=_auth(token),
            files={"file": ("hello.exe", b"MZ junk", "application/octet-stream")},
        )
    assert r.status_code == 415


def test_upload_rejects_oversize(app, token, tmp_inbox, monkeypatch) -> None:
    """Hard size cap protects the backend from OOM via a long-running upload."""
    from printwatcher.server.routes import upload as upload_module

    # Drop the cap to keep the test fast; the production cap is 50 MB.
    monkeypatch.setattr(upload_module, "_MAX_UPLOAD_BYTES", 1024)
    too_big = b"%PDF-1.4 " + b"A" * 4096

    client = TestClient(app)
    with client:
        r = client.post(
            "/api/inbox/drop",
            headers=_auth(token),
            files={"file": ("big.pdf", too_big, "application/pdf")},
        )
    assert r.status_code == 413
    # Partial file must not be left behind on the inbox.
    assert not (tmp_inbox / "big.pdf").exists()


def test_upload_sanitizes_filename(app, token, tmp_inbox) -> None:
    """Path-traversal attempts are stripped down to the basename and
    special characters are replaced with underscores."""
    client = TestClient(app)
    with client:
        r = client.post(
            "/api/inbox/drop",
            headers=_auth(token),
            files={"file": ("../../etc/passwd.pdf", b"%PDF-1.4 x", "application/pdf")},
        )
    assert r.status_code == 200
    # File must land in the inbox, not above it.
    landed = list(tmp_inbox.glob("*.pdf"))
    assert len(landed) == 1
    assert landed[0].parent == tmp_inbox
    # Pin the exact basename so a regression that drops the Path(...).name
    # call in _sanitize would surface here.
    assert landed[0].name == "passwd.pdf"


def test_upload_requires_token(app) -> None:
    client = TestClient(app)
    with client:
        r = client.post(
            "/api/inbox/drop",
            files={"file": ("x.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert r.status_code == 401
