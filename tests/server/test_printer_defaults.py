"""``/api/printer-defaults`` — per-printer option presets persisted in prefs.json."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from printwatcher.core import PrintOptions, _apply_printer_defaults


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def isolated_prefs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect preferences.json to a tmp file so the suite doesn't touch
    %APPDATA%/PrintWatcher."""
    prefs_file = tmp_path / "preferences.json"
    monkeypatch.setattr("printwatcher.core._preferences_path", lambda: prefs_file)
    return prefs_file


def test_put_then_get_round_trip(app, token, isolated_prefs) -> None:
    client = TestClient(app)
    payload = {"color": "color", "sides": "duplex", "copies": 2}
    with client:
        put = client.put("/api/printer-defaults/ColorLaser", headers=_auth(token), json=payload)
        assert put.status_code == 200, put.text
        get = client.get("/api/printer-defaults/ColorLaser", headers=_auth(token))
    assert get.status_code == 200
    assert get.json() == {**payload, "printer": None}


def test_get_missing_is_404(app, token, isolated_prefs) -> None:
    client = TestClient(app)
    with client:
        r = client.get("/api/printer-defaults/Unknown", headers=_auth(token))
    assert r.status_code == 404


def test_list_returns_all_registered(app, token, isolated_prefs) -> None:
    client = TestClient(app)
    with client:
        client.put("/api/printer-defaults/A", headers=_auth(token), json={"color": "color"})
        client.put("/api/printer-defaults/B", headers=_auth(token), json={"color": "monochrome"})
        r = client.get("/api/printer-defaults", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"A", "B"}
    assert body["A"]["color"] == "color"
    assert body["B"]["color"] == "monochrome"


def test_delete_removes(app, token, isolated_prefs) -> None:
    client = TestClient(app)
    with client:
        client.put("/api/printer-defaults/Doomed", headers=_auth(token), json={"color": "color"})
        r = client.delete("/api/printer-defaults/Doomed", headers=_auth(token))
        assert r.status_code == 204
        miss = client.get("/api/printer-defaults/Doomed", headers=_auth(token))
    assert miss.status_code == 404


def test_requires_token(app) -> None:
    client = TestClient(app)
    with client:
        r = client.get("/api/printer-defaults")
    assert r.status_code == 401


# --- precedence: defaults fill gaps; explicit values win --------------------

def test_defaults_fill_unset_fields() -> None:
    options = PrintOptions(printer="ColorLaser", copies=1, sides=None, color=None)
    defaults = {"ColorLaser": {"color": "color", "sides": "duplex", "copies": 3}}
    out = _apply_printer_defaults(options, defaults)
    assert out.color == "color"
    assert out.sides == "duplex"
    assert out.copies == 3


def test_defaults_do_not_override_explicit() -> None:
    options = PrintOptions(printer="ColorLaser", copies=5, sides="simplex", color="monochrome")
    defaults = {"ColorLaser": {"color": "color", "sides": "duplex", "copies": 99}}
    out = _apply_printer_defaults(options, defaults)
    assert out.color == "monochrome"  # explicit user value wins
    assert out.sides == "simplex"
    assert out.copies == 5


def test_defaults_skip_when_no_printer() -> None:
    options = PrintOptions(printer=None)
    defaults = {"ColorLaser": {"color": "color"}}
    assert _apply_printer_defaults(options, defaults) == options


def test_defaults_skip_when_no_match() -> None:
    options = PrintOptions(printer="OtherPrinter")
    defaults = {"ColorLaser": {"color": "color"}}
    assert _apply_printer_defaults(options, defaults) == options
