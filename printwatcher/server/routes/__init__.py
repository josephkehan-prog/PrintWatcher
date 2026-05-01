"""Per-resource FastAPI routers."""

from printwatcher.server.routes import (
    history,
    options,
    pending,
    prefs,
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
    history.router,
    pending.router,
    prefs.router,
    themes.router,
    tools.router,
    upload.router,
    shutdown.router,
)
