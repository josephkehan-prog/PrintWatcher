"""``GET /api/state`` boot snapshot + ``POST /api/pause``."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from printwatcher.core import APP_VERSION, list_printers, load_preferences
from printwatcher.server.auth import require_token
from printwatcher.server.dto import (
    PauseDto,
    PendingItemDto,
    PreferencesDto,
    PrintersDto,
    PrintOptionsDto,
    StateDto,
    StatsDto,
)
from printwatcher.server.state import AppState, get_state

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


def _pending_items(state: AppState) -> list[PendingItemDto]:
    return [
        PendingItemDto(path=str(p), name=p.name)
        for p in state.watcher.pending_paths()
    ]


def _printers_snapshot() -> PrintersDto:
    names = list_printers()
    return PrintersDto(default=names[0] if names else None, list=names)


@router.get("/state", response_model=StateDto)
def get_state_snapshot(state: AppState = Depends(get_state)) -> StateDto:
    prefs = load_preferences()
    return StateDto(
        version=state.app_version or APP_VERSION,
        stats=StatsDto(**state.watcher.stats),
        paused=state.watcher.is_paused,
        options=PrintOptionsDto.from_core(state.watcher.get_options()),
        pending=_pending_items(state),
        preferences=PreferencesDto(
            theme=prefs.get("theme", "Ocean"),
            hold_mode=bool(prefs.get("hold_mode", False)),
            larger_text=bool(prefs.get("larger_text", False)),
            reduce_transparency=bool(prefs.get("reduce_transparency", False)),
        ),
        printers=_printers_snapshot(),
    )


@router.post("/pause", response_model=PauseDto)
def post_pause(payload: PauseDto, state: AppState = Depends(get_state)) -> PauseDto:
    state.watcher.set_paused(payload.paused)
    state.events.publish({"type": "paused", "paused": state.watcher.is_paused})
    return PauseDto(paused=state.watcher.is_paused)


@router.get("/version")
def get_version(state: AppState = Depends(get_state)) -> dict[str, str]:
    import platform
    return {
        "app": state.app_version or APP_VERSION,
        "server": "fastapi",
        "python": platform.python_version(),
    }
