"""History query endpoints with substring + regex filtering."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, status

from printwatcher.server.auth import require_token
from printwatcher.server.dto import PrintRecordDto
from printwatcher.server.state import AppState, get_state

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@router.get("/history", response_model=list[PrintRecordDto])
def list_history(
    state: AppState = Depends(get_state),
    limit: int = Query(default=200, ge=1, le=200),
    q: str | None = Query(default=None),
    regex: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
) -> list[PrintRecordDto]:
    records = state.watcher.history.recent()

    if q:
        needle = q.lower()
        records = [r for r in records if needle in r.filename.lower() or needle in r.submitter.lower()]

    if regex:
        try:
            pattern = re.compile(regex, re.IGNORECASE)
        except re.error as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid regex: {exc}",
            )
        records = [r for r in records if pattern.search(r.filename) or pattern.search(r.submitter)]

    if from_:
        records = [r for r in records if r.timestamp >= from_]
    if to:
        records = [r for r in records if r.timestamp <= to]

    return [PrintRecordDto.from_core(r) for r in records[:limit]]


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(state: AppState = Depends(get_state)) -> None:
    state.watcher.history.clear()
    state.events.publish({"type": "history-cleared"})
