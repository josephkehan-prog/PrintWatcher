"""PrintWatcher core package — UI-agnostic watcher state and FastAPI surface.

Every public name needed by the Tk UI and the FastAPI backend is re-exported
here. Treat this as the stable API; consumers should import from
``printwatcher`` rather than reaching into submodules.
"""

from __future__ import annotations

from printwatcher.core import (
    APP_VERSION,
    COLOR_CHOICES,
    DEFAULT_PRINTER_LABEL,
    DEFAULT_SUMATRA,
    DEFAULT_THEME,
    EXTS,
    LOG_LINE_LIMIT,
    POLL_INTERVAL_SEC,
    PRINTED_SUBDIR,
    RESERVED_TOP_LEVEL,
    SCHEDULED_SUBDIR,
    SIDES_CHOICES,
    SKIPPED_SUBDIR,
    STABLE_CHECKS,
    STABLE_INTERVAL_SEC,
    THEMES,
    HistoryStore,
    InboxHandler,
    PrintOptions,
    PrintRecord,
    PrinterWorker,
    WatcherCore,
    default_history_path,
    discover_paths,
    list_printers,
    load_preferences,
    parse_filename_options,
    resolve_path_options,
    save_preferences,
    split_label,
)

__all__ = [
    "APP_VERSION",
    "COLOR_CHOICES",
    "DEFAULT_PRINTER_LABEL",
    "DEFAULT_SUMATRA",
    "DEFAULT_THEME",
    "EXTS",
    "HistoryStore",
    "InboxHandler",
    "LOG_LINE_LIMIT",
    "POLL_INTERVAL_SEC",
    "PRINTED_SUBDIR",
    "PrintOptions",
    "PrintRecord",
    "PrinterWorker",
    "RESERVED_TOP_LEVEL",
    "SCHEDULED_SUBDIR",
    "SIDES_CHOICES",
    "SKIPPED_SUBDIR",
    "STABLE_CHECKS",
    "STABLE_INTERVAL_SEC",
    "THEMES",
    "WatcherCore",
    "default_history_path",
    "discover_paths",
    "list_printers",
    "load_preferences",
    "parse_filename_options",
    "resolve_path_options",
    "save_preferences",
    "split_label",
]
