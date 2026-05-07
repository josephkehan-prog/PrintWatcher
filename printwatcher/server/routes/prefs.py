"""``GET/PUT /api/preferences`` — theme + accessibility toggles."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from printwatcher.core import save_preferences
from printwatcher.server.auth import require_token
from printwatcher.server.dto import PreferencesDto
from printwatcher.server.state import AppState, get_state

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@router.get("/preferences", response_model=PreferencesDto)
def get_prefs(state: AppState = Depends(get_state)) -> PreferencesDto:
    raw = state.get_preferences()
    return PreferencesDto(
        theme=raw.get("theme", "Ocean"),
        hold_mode=bool(raw.get("hold_mode", False)),
        larger_text=bool(raw.get("larger_text", False)),
        reduce_transparency=bool(raw.get("reduce_transparency", False)),
    )


@router.put("/preferences", response_model=PreferencesDto)
def put_prefs(
    payload: PreferencesDto,
    state: AppState = Depends(get_state),
) -> PreferencesDto:
    raw = state.get_preferences()
    raw.update(payload.model_dump())
    save_preferences(raw)
    state.invalidate_preferences(fresh=raw)
    return payload
