"""Ensure submitter resolution + path discovery don't regress."""

from __future__ import annotations


def test_submitter_for_root_drop(watcher_module, tmp_inbox):
    submitter = watcher_module._submitter_for(tmp_inbox / "doc.pdf", tmp_inbox)
    assert submitter   # falls back to local user (non-empty)


def test_submitter_for_subfolder(watcher_module, tmp_inbox):
    submitter = watcher_module._submitter_for(
        tmp_inbox / "MaryDoe" / "doc.pdf", tmp_inbox,
    )
    assert submitter == "MaryDoe"


def test_submitter_strips_options_from_first_segment(watcher_module, tmp_inbox):
    """Submitter folder Class3__copies=30 attributes to "Class3", not the whole label."""
    submitter = watcher_module._submitter_for(
        tmp_inbox / "Class3__copies=30_duplex" / "doc.pdf", tmp_inbox,
    )
    assert submitter == "Class3"


def test_submitter_bare_preset_falls_back(watcher_module, tmp_inbox):
    submitter = watcher_module._submitter_for(
        tmp_inbox / "__copies=30" / "doc.pdf", tmp_inbox,
    )
    # Bare preset -> no submitter override, fall back to OS user
    assert submitter   # non-empty
    assert submitter != "__copies=30"


def test_split_label_no_separator(watcher_module):
    assert watcher_module.split_label("plain") == ("plain", "")


def test_split_label_with_options(watcher_module):
    name, opts = watcher_module.split_label("MaryDoe__copies=30")
    assert name == "MaryDoe"
    assert opts == "copies=30"


def test_split_label_empty_name(watcher_module):
    name, opts = watcher_module.split_label("__copies=30")
    assert name == ""
    assert opts == "copies=30"


def test_helper_labels(watcher_module):
    assert watcher_module._sides_label("duplex") == "duplex (long)"
    assert watcher_module._sides_label("duplexshort") == "duplex (short)"
    assert watcher_module._sides_label("simplex") == "single"
    assert watcher_module._sides_label(None) == "default"
    assert watcher_module._color_label("color") == "color"
    assert watcher_module._color_label("monochrome") == "mono"
    assert watcher_module._color_label(None) == "default"


def test_local_user_returns_something(watcher_module):
    assert watcher_module._local_user()  # non-empty under any env
