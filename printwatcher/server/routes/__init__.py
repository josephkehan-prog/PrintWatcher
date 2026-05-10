"""Per-resource FastAPI routers."""

from printwatcher.server.routes import (
    history,
    inbox,
    options,
    pending,
    prefs,
    printer_defaults,
    printers,
    shutdown,
    state,
    themes,
    tools,
    upload,
)

ALL_ROUTERS = (
    state.router,
    options.router,
    printers.router,
    printer_defaults.router,
    history.router,
    pending.router,
    prefs.router,
    themes.router,
    tools.router,
    upload.router,
    inbox.router,
    shutdown.router,
)
