"""``GET /api/inbox/health`` — disk usage + file counts for the watched inbox."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from printwatcher.server.auth import require_token
from printwatcher.server.dto import InboxHealthDto
from printwatcher.server.state import AppState, get_state

router = APIRouter(prefix="/api/inbox", dependencies=[Depends(require_token)])


@router.get("/health", response_model=InboxHealthDto)
def inbox_health(state: AppState = Depends(get_state)) -> InboxHealthDto:
    return InboxHealthDto(**state.watcher.inbox_health())
