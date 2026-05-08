"""History query endpoints with substring + regex filtering."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from printwatcher.server.auth import require_token
from printwatcher.server.dto import PrintRecordDto, record_id
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
    status_filter: str | None = Query(default=None, alias="status"),
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
            ) from exc
        records = [r for r in records if pattern.search(r.filename) or pattern.search(r.submitter)]

    if from_:
        records = [r for r in records if r.timestamp >= from_]
    if to:
        records = [r for r in records if r.timestamp <= to]
    if status_filter:
        records = [r for r in records if r.status == status_filter]

    return [PrintRecordDto.from_core(r) for r in records[:limit]]


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(state: AppState = Depends(get_state)) -> None:
    state.watcher.history.clear()
    state.events.publish({"type": "history-cleared"})


@router.post("/history/{record_id_param}/reprint", response_model=PrintRecordDto)
def reprint_record(
    record_id_param: str = Path(..., min_length=8, max_length=64),
    state: AppState = Depends(get_state),
) -> PrintRecordDto:
    """Re-queue a previously-printed file by id.

    The id is the prefix-of-sha1 derived in ``dto.record_id``; it survives
    process restart because the inputs come from history.json.
    """
    match = next(
        (r for r in state.watcher.history.recent() if record_id(r) == record_id_param),
        None,
    )
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"history record not found: {record_id_param}",
        )
    try:
        state.watcher.reprint(match)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(exc),
        ) from exc
    return PrintRecordDto.from_core(match)
