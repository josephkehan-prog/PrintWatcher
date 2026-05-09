"""``POST /api/history/{id}/reprint`` — copy a printed file back to the inbox."""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from printwatcher.core import PrintRecord, PRINTED_SUBDIR
from printwatcher.server.dto import record_id


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed(watcher, filename: str = "report.pdf", submitter: str = "alice") -> PrintRecord:
    """Drop a 'printed' file under _printed/<submitter>/ and append history."""
    rec = PrintRecord(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        filename=filename,
        status="ok",
        printer="LaserJet",
        copies=1,
        submitter=submitter,
    )
    watcher.history.append(rec)
    printed = watcher.watch_dir / PRINTED_SUBDIR / submitter
    printed.mkdir(parents=True, exist_ok=True)
    (printed / filename).write_bytes(b"%PDF-1.4 reprint-source")
    return rec


def test_reprint_copies_back_to_inbox(app, watcher, token, tmp_inbox) -> None:
    rec = _seed(watcher)
    client = TestClient(app)
    with client:
        r = client.post(f"/api/history/{record_id(rec)}/reprint", headers=_auth(token))

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"] == "report.pdf"
    assert (tmp_inbox / "report.pdf").exists()


def test_reprint_collision_uses_unique_stem(app, watcher, token, tmp_inbox) -> None:
    """If the original filename already exists in the inbox, the reprinted
    copy lands as <stem>-reprint.<ext>."""
    rec = _seed(watcher)
    (tmp_inbox / "report.pdf").write_bytes(b"already here")  # block the canonical name

    client = TestClient(app)
    with client:
        r = client.post(f"/api/history/{record_id(rec)}/reprint", headers=_auth(token))

    assert r.status_code == 200
    assert (tmp_inbox / "report.pdf").read_bytes() == b"already here"  # untouched
    assert (tmp_inbox / "report-reprint.pdf").exists()


def test_reprint_missing_id_is_404(app, token) -> None:
    client = TestClient(app)
    with client:
        r = client.post("/api/history/deadbeefdeadbeef/reprint", headers=_auth(token))
    assert r.status_code == 404


def test_reprint_source_gone_is_410(app, watcher, token) -> None:
    """If the printed file has been deleted from disk, /reprint returns 410 Gone."""
    rec = _seed(watcher, filename="ghost.pdf")
    # Now delete the source so the copy fails.
    (watcher.watch_dir / PRINTED_SUBDIR / rec.submitter / rec.filename).unlink()

    client = TestClient(app)
    with client:
        r = client.post(f"/api/history/{record_id(rec)}/reprint", headers=_auth(token))
    assert r.status_code == 410


def test_reprint_requires_token(app, watcher) -> None:
    rec = _seed(watcher)
    client = TestClient(app)
    with client:
        r = client.post(f"/api/history/{record_id(rec)}/reprint")
    assert r.status_code == 401


def test_reprint_rejects_path_traversal_in_filename(app, watcher, token, tmp_inbox) -> None:
    """A historic record whose filename escapes the inbox via ../ must not
    cause the copy target (or source lookup) to leave watch_dir."""
    # Build a record with a malformed filename and a real source on disk that
    # the unsanitized code path would have copied through.
    rec = PrintRecord(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        filename="../escaped.pdf",  # tries to escape watch_dir
        status="ok",
        printer="LaserJet",
        submitter="alice",
    )
    watcher.history.append(rec)
    # Place a "matching" source under the basename so the canonical lookup
    # would succeed; if reprint sanitizes correctly, the target lands inside
    # tmp_inbox under "escaped.pdf" — never above tmp_inbox.
    printed = tmp_inbox / PRINTED_SUBDIR / "alice"
    printed.mkdir(parents=True, exist_ok=True)
    (printed / "escaped.pdf").write_bytes(b"%PDF-1.4 source")

    client = TestClient(app)
    with client:
        r = client.post(f"/api/history/{record_id(rec)}/reprint", headers=_auth(token))

    # The basename-only path lands inside tmp_inbox, never above.
    assert r.status_code == 200
    assert (tmp_inbox / "escaped.pdf").exists()
    assert not (tmp_inbox.parent / "escaped.pdf").exists()


def test_reprint_rejects_dot_filename(app, watcher, token) -> None:
    """A degenerate filename (".", "..", "") yields 410 — basename strips to nothing."""
    rec = PrintRecord(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        filename="..",
        status="ok",
        printer="LaserJet",
        submitter="bob",
    )
    watcher.history.append(rec)
    client = TestClient(app)
    with client:
        r = client.post(f"/api/history/{record_id(rec)}/reprint", headers=_auth(token))
    assert r.status_code == 410
