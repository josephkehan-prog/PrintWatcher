"""``GET/PUT /api/options`` — current PrintOptions."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from printwatcher.server.auth import require_token
from printwatcher.server.dto import PrintOptionsDto
from printwatcher.server.state import AppState, get_state

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@router.get("/options", response_model=PrintOptionsDto)
def get_options(state: AppState = Depends(get_state)) -> PrintOptionsDto:
    return PrintOptionsDto.from_core(state.watcher.get_options())


@router.put("/options", response_model=PrintOptionsDto)
def put_options(
    payload: PrintOptionsDto,
    state: AppState = Depends(get_state),
) -> PrintOptionsDto:
    new_options = payload.to_core()
    state.watcher.set_options(new_options)
    state.events.publish({"type": "options", "options": payload.model_dump()})
    return PrintOptionsDto.from_core(new_options)
