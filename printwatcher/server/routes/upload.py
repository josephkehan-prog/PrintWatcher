"""``POST /api/inbox/drop`` — drag-drop file upload from the WinUI shell."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from printwatcher.core import EXTS
from printwatcher.server.auth import require_token
from printwatcher.server.state import AppState, get_state

router = APIRouter(prefix="/api/inbox", dependencies=[Depends(require_token)])

_SAFE_NAME = re.compile(r"[^\w\-. ]+")


def _sanitize(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", Path(name).name).strip()
    return cleaned or "upload"


@router.post("/drop")
async def drop(file: UploadFile, state: AppState = Depends(get_state)) -> dict[str, str]:
    name = _sanitize(file.filename or "upload")
    suffix = Path(name).suffix.lower()
    if suffix not in EXTS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"unsupported extension: {suffix}",
        )
    target = state.watcher.watch_dir / name
    if target.exists():
        target = target.with_stem(f"{target.stem}-upload")
    contents = await file.read()
    target.write_bytes(contents)
    return {"path": str(target), "name": target.name}
