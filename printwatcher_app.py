"""Unified PrintWatcher launcher — desktop UI plus every companion CLI.

Behavior

    PrintWatcher.exe                       # launches the desktop UI
    PrintWatcher.exe ui                    # same — explicit
    PrintWatcher.exe tray                  # legacy tray-only watcher
    PrintWatcher.exe watcher               # minimal CLI watcher
    PrintWatcher.exe <subcommand> [args]   # runs the matching helper script
    PrintWatcher.exe --list                # show every subcommand

Subcommand names follow the script filenames with `_` replaced by `-`. So
`scripts/pdf_inspect.py` is `pdf-inspect`, `scripts/clear_queue.py` is
`clear-queue`, etc.

Every script's `--help` is forwarded transparently:

    PrintWatcher.exe roster --help
    PrintWatcher.exe pdf-inspect --help

When frozen with PyInstaller, `sys._MEIPASS` is set; resource lookups
inside the bundle still work because PyInstaller adds the extraction
directory to sys.path automatically.
"""

from __future__ import annotations

import importlib
import sys
from typing import Iterable

# Keep in sync with print_watcher_ui.APP_VERSION and pyproject.toml.
APP_VERSION = "0.3.0"

# Subcommand → fully-qualified module name. Each module exposes a
# `main(argv: list[str] | None) -> int` callable.
SUBCOMMANDS: dict[str, str] = {
    "ui": "print_watcher_ui",
    "tray": "print_watcher_tray",
    "watcher": "print_watcher",
    "backend": "printwatcher.server.__main__",
    # PDF tools
    "pdf-inspect": "scripts.pdf_inspect",
    "pdf-merge": "scripts.pdf_merge",
    "pdf-compress": "scripts.pdf_compress",
    "pdf-split": "scripts.pdf_split",
    "pdf-watermark": "scripts.pdf_watermark",
    "redact": "scripts.redact",
    "name-stamper": "scripts.name_stamper",
    "roster-split": "scripts.roster_split",
    # Roster / class management
    "roster": "scripts.roster",
    "portfolio": "scripts.student_portfolio",
    "parent-letter": "scripts.parent_letter",
    "attendance": "scripts.attendance_sheet",
    "seating": "scripts.seating_chart",
    "sub-packet": "scripts.sub_packet",
    # Inbox housekeeping
    "verify": "scripts.verify_environment",
    "dedupe": "scripts.dedupe_inbox",
    "cleanup": "scripts.cleanup_printed",
    "clear-queue": "scripts.clear_queue",
    "presets": "scripts.setup_inbox_presets",
    "printer-test": "scripts.printer_test",
    # Workflow daemons
    "schedule": "scripts.schedule_print",
    "auto-merge": "scripts.auto_merge",
    "email": "scripts.email_to_inbox",
    "screenshot": "scripts.screenshot_to_print",
    # Reporting / utility
    "report": "scripts.weekly_report",
    "history-search": "scripts.history_search",
    "web-to-pdf": "scripts.web_to_pdf",
    "preview-shortcut": "scripts.preview_shortcut_path",
}

# Categories used only when rendering --list for humans.
GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Watcher",        ("ui", "tray", "watcher", "backend")),
    ("PDF tools",      ("pdf-inspect", "pdf-merge", "pdf-compress",
                        "pdf-split", "pdf-watermark", "redact",
                        "name-stamper", "roster-split")),
    ("Rosters",        ("roster", "portfolio", "parent-letter",
                        "attendance", "seating", "sub-packet")),
    ("Inbox hygiene",  ("verify", "dedupe", "cleanup", "clear-queue",
                        "presets", "printer-test")),
    ("Daemons",        ("schedule", "auto-merge", "email", "screenshot")),
    ("Reporting",      ("report", "history-search", "web-to-pdf",
                        "preview-shortcut")),
)


def _print_help() -> None:
    print("PrintWatcher — unified launcher")
    print()
    print("Usage:")
    print("  PrintWatcher [<subcommand> [args...]]")
    print()
    print("With no subcommand the desktop UI launches. Pass --help to any")
    print("subcommand to see its own options:")
    print()
    print("  PrintWatcher roster --help")
    print("  PrintWatcher pdf-inspect packet.pdf")
    print("  PrintWatcher report --to-inbox")
    print()
    for label, names in GROUPS:
        print(f"{label}:")
        for name in names:
            module = SUBCOMMANDS[name]
            print(f"  {name:<20s} {module}")
        print()


def _resolve(name: str) -> str | None:
    """Map a (possibly fuzzy) subcommand to a module path."""
    if name in SUBCOMMANDS:
        return SUBCOMMANDS[name]
    # accept underscore variants (scripts use snake_case)
    candidate = name.replace("_", "-")
    if candidate in SUBCOMMANDS:
        return SUBCOMMANDS[candidate]
    return None


def _dispatch(argv: list[str]) -> int:
    if not argv:
        return _launch_ui()
    head = argv[0]
    if head in ("-h", "--help", "help"):
        _print_help()
        return 0
    if head in ("--list", "list"):
        for name in sorted(SUBCOMMANDS):
            print(name)
        return 0
    if head in ("--version", "-V"):
        print(f"PrintWatcher {APP_VERSION}")
        return 0

    module_name = _resolve(head)
    if module_name is None:
        print(f"Unknown subcommand: {head!r}\n", file=sys.stderr)
        _print_help()
        return 2
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        print(f"Could not import {module_name}: {exc}", file=sys.stderr)
        return 2
    if not hasattr(module, "main"):
        print(f"{module_name} has no main() entry point", file=sys.stderr)
        return 2
    return module.main(argv[1:])


def _launch_ui() -> int:
    from print_watcher_ui import main as ui_main
    ui_main()
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    return _dispatch(list(argv))


if __name__ == "__main__":
    raise SystemExit(main())
