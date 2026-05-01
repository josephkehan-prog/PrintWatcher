"""FastAPI surface that exposes the watcher state to the WinUI 3 shell.

See ``printwatcher/server/__main__.py`` for the CLI entry point that boots a
``WatcherCore``, runs uvicorn, and writes the discovery file the C# shell
polls for ``{port, token}``.
"""

from printwatcher.server.app import create_app
from printwatcher.server.events import EventBus
from printwatcher.server.state import AppState

__all__ = ["AppState", "EventBus", "create_app"]
