"""Hold-and-release queue endpoints."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from printwatcher.core import SKIPPED_SUBDIR
from printwatcher.server.auth import require_token
from printwatcher.server.dto import PendingItemDto
from printwatcher.server.state import AppState, get_state

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


def _ensure_under_watch(p: Path, watch: Path) -> None:
    try:
        p.resolve().relative_to(watch.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="path is outside watch dir",
        ) from exc


@router.get("/pending", response_model=list[PendingItemDto])
def list_pending(state: AppState = Depends(get_state)) -> list[PendingItemDto]:
    return [
        PendingItemDto(path=str(p), name=p.name)
        for p in state.watcher.pending_paths()
    ]


@router.post("/pending/print")
def release_pending(state: AppState = Depends(get_state)) -> dict[str, int]:
    """Resume any paused worker so the queued items print.

    Worker keeps the same in-flight set; nothing more to do beyond clearing
    the pause flag. The hold-mode preference is the user's responsibility to
    toggle separately via ``PUT /api/preferences``.
    """
    state.watcher.resume()
    return {"released": len(state.watcher.pending_paths())}


@router.post("/pending/skip")
def skip_pending(state: AppState = Depends(get_state)) -> dict[str, int]:
    """Move every in-flight file to ``_skipped/`` and forget it."""
    moved = 0
    skipped_dir = state.watcher.watch_dir / SKIPPED_SUBDIR
    skipped_dir.mkdir(parents=True, exist_ok=True)
    for path in state.watcher.pending_paths():
        _ensure_under_watch(path, state.watcher.watch_dir)
        if not path.exists():
            continue
        try:
            shutil.move(str(path), skipped_dir / path.name)
            moved += 1
        except OSError:
            continue
    state.events.publish({"type": "pending", "items": []})
    return {"skipped": moved}
