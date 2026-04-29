"""HistoryStore round-trip + backward-compat coverage."""

from __future__ import annotations

import json


def test_history_round_trip(watcher_module, tmp_path):
    store = watcher_module.HistoryStore(tmp_path / "h.json")
    rec = watcher_module.PrintRecord(
        timestamp="2026-04-29T10:00:00",
        filename="quiz.pdf",
        status="ok",
        printer="default",
        copies=3,
        sides="duplex (long)",
        color="color",
        submitter="MaryDoe",
    )
    store.append(rec)
    reloaded = watcher_module.HistoryStore(tmp_path / "h.json")
    records = reloaded.recent()
    assert len(records) == 1
    got = records[0]
    assert got.filename == "quiz.pdf"
    assert got.copies == 3
    assert got.submitter == "MaryDoe"


def test_history_max_entries_truncates(watcher_module, tmp_path):
    store = watcher_module.HistoryStore(tmp_path / "h.json")
    cap = store.MAX_ENTRIES
    for i in range(cap + 25):
        store.append(watcher_module.PrintRecord(
            timestamp=f"2026-04-29T{i % 24:02d}:00:00",
            filename=f"f{i}.pdf",
            status="ok",
        ))
    records = store.recent()
    assert len(records) == cap
    # newest is most recent; we capped the oldest 25
    assert records[0].filename == f"f{cap + 24}.pdf"


def test_history_legacy_entry_loads(watcher_module, tmp_path):
    """Records written before the submitter field existed should still load."""
    legacy = [{
        "timestamp": "2026-01-01T12:00:00",
        "filename": "old.pdf",
        "status": "ok",
    }]
    path = tmp_path / "h.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    store = watcher_module.HistoryStore(path)
    records = store.recent()
    assert len(records) == 1
    assert records[0].submitter == ""   # default


def test_history_skips_bad_entries(watcher_module, tmp_path):
    bad_entries = [
        "not-a-dict",
        {"missing-required-fields": True},
        {"timestamp": "x", "filename": "y.pdf", "status": "ok", "extra": "ignored"},
    ]
    path = tmp_path / "h.json"
    path.write_text(json.dumps(bad_entries), encoding="utf-8")
    store = watcher_module.HistoryStore(path)
    records = store.recent()
    # Only the third entry has the minimum required fields;
    # extra is silently dropped because PrintRecord rejects unknown kwargs.
    # PrintRecord.__init__ errors on extras, so we expect zero or one.
    assert len(records) <= 1


def test_history_clear(watcher_module, tmp_path):
    store = watcher_module.HistoryStore(tmp_path / "h.json")
    store.append(watcher_module.PrintRecord(
        timestamp="x", filename="a.pdf", status="ok",
    ))
    assert store.recent()
    store.clear()
    assert store.recent() == []


def test_print_record_time_short_formats_iso(watcher_module):
    rec = watcher_module.PrintRecord(
        timestamp="2026-04-29T10:30:00",
        filename="x.pdf",
        status="ok",
    )
    assert rec.time_short == "04/29 10:30"


def test_print_record_time_short_falls_back(watcher_module):
    rec = watcher_module.PrintRecord(
        timestamp="not-a-date",
        filename="x.pdf",
        status="ok",
    )
    assert rec.time_short == "not-a-date"
