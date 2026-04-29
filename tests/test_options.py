"""Filename + folder option parser coverage."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_parse_filename_options_no_separator(watcher_module):
    base = watcher_module.PrintOptions()
    merged, tokens = watcher_module.parse_filename_options("plain.pdf", base)
    assert merged == base
    assert tokens == []


def test_parse_filename_options_copies(watcher_module):
    base = watcher_module.PrintOptions()
    merged, tokens = watcher_module.parse_filename_options("worksheet__copies=30.pdf", base)
    assert merged.copies == 30
    assert "copies=30" in tokens


def test_parse_filename_options_combined(watcher_module):
    base = watcher_module.PrintOptions()
    merged, tokens = watcher_module.parse_filename_options(
        "quiz__copies=12_duplex_color.pdf", base,
    )
    assert merged.copies == 12
    assert merged.sides == "duplex"
    assert merged.color == "color"
    assert "copies=12" in tokens
    assert "duplex" in tokens
    assert "color" in tokens


def test_parse_filename_options_clamps_copies(watcher_module):
    base = watcher_module.PrintOptions()
    high, _ = watcher_module.parse_filename_options("x__copies=999.pdf", base)
    low, _ = watcher_module.parse_filename_options("x__copies=0.pdf", base)
    bad, _ = watcher_module.parse_filename_options("x__copies=garbage.pdf", base)
    assert high.copies == 99
    assert low.copies == 1
    assert bad.copies == base.copies   # untouched


def test_parse_filename_options_ignores_bare_separator(watcher_module):
    base = watcher_module.PrintOptions()
    merged, tokens = watcher_module.parse_filename_options("__copies=30.pdf", base)
    # No `name` part, the parser does not apply the overlay (it's reserved
    # for folder presets where bare-prefix is meaningful).
    assert merged == base
    assert tokens == []


def test_parse_filename_options_synonyms(watcher_module):
    base = watcher_module.PrintOptions()
    duplex_short, _ = watcher_module.parse_filename_options("x__short.pdf", base)
    mono, _ = watcher_module.parse_filename_options("x__bw.pdf", base)
    color, _ = watcher_module.parse_filename_options("x__colour.pdf", base)
    assert duplex_short.sides == "duplexshort"
    assert mono.color == "monochrome"
    assert color.color == "color"


def test_resolve_path_options_root(watcher_module, tmp_inbox):
    base = watcher_module.PrintOptions()
    merged, tokens, submitter = watcher_module.resolve_path_options(
        tmp_inbox / "doc.pdf", tmp_inbox, base,
    )
    assert merged == base
    assert tokens == []
    # Submitter falls back to current OS user
    assert submitter


def test_resolve_path_options_submitter_folder(watcher_module, tmp_inbox):
    base = watcher_module.PrintOptions()
    _, _, submitter = watcher_module.resolve_path_options(
        tmp_inbox / "MaryDoe" / "doc.pdf", tmp_inbox, base,
    )
    assert submitter == "MaryDoe"


def test_resolve_path_options_preset_folder(watcher_module, tmp_inbox):
    base = watcher_module.PrintOptions()
    merged, tokens, submitter = watcher_module.resolve_path_options(
        tmp_inbox / "__copies=30" / "doc.pdf", tmp_inbox, base,
    )
    assert merged.copies == 30
    assert "copies=30" in tokens
    # Bare-prefix folder name -> no submitter override
    assert submitter and submitter != "__copies=30"


def test_resolve_path_options_combined_folder(watcher_module, tmp_inbox):
    base = watcher_module.PrintOptions()
    merged, tokens, submitter = watcher_module.resolve_path_options(
        tmp_inbox / "Class3__copies=30_duplex" / "doc.pdf", tmp_inbox, base,
    )
    assert submitter == "Class3"
    assert merged.copies == 30
    assert merged.sides == "duplex"


def test_resolve_path_options_filename_overrides_folder(watcher_module, tmp_inbox):
    base = watcher_module.PrintOptions()
    merged, _tokens, _sub = watcher_module.resolve_path_options(
        tmp_inbox / "MaryDoe__duplex" / "doc__copies=2.pdf", tmp_inbox, base,
    )
    assert merged.copies == 2
    assert merged.sides == "duplex"


def test_resolve_path_options_nested_preset(watcher_module, tmp_inbox):
    base = watcher_module.PrintOptions()
    merged, _t, submitter = watcher_module.resolve_path_options(
        tmp_inbox / "MaryDoe" / "__copies=30" / "doc.pdf", tmp_inbox, base,
    )
    assert submitter == "MaryDoe"
    assert merged.copies == 30


def test_resolve_path_options_outside_inbox(watcher_module, tmp_inbox, tmp_path):
    base = watcher_module.PrintOptions()
    merged, tokens, submitter = watcher_module.resolve_path_options(
        tmp_path / "elsewhere.pdf", tmp_inbox, base,
    )
    assert merged == base
    assert tokens == []
    assert submitter   # falls back to local user


def test_print_options_to_sumatra_args(watcher_module):
    options = watcher_module.PrintOptions(
        printer="Printix Anywhere",
        copies=3,
        sides="duplex",
        color="color",
    )
    args = options.to_sumatra_args(Path("C:/sumatra.exe"), Path("C:/file.pdf"))
    assert "-print-to" in args
    assert "Printix Anywhere" in args
    assert "-print-settings" in args
    settings_idx = args.index("-print-settings") + 1
    assert "3x" in args[settings_idx]
    assert "duplex" in args[settings_idx]
    assert "color" in args[settings_idx]


def test_print_options_default_no_settings(watcher_module):
    options = watcher_module.PrintOptions()
    args = options.to_sumatra_args(Path("C:/s.exe"), Path("C:/f.pdf"))
    assert "-print-to-default" in args
    assert "-print-settings" not in args
