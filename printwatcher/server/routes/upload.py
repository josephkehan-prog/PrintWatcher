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
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB — generous for PDFs, blocks runaway uploads.
_CHUNK = 1024 * 1024  # 1 MB streaming chunks


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

    # Stream to disk with a hard size cap so a malicious or buggy client
    # holding a valid token can't OOM the backend by uploading a 10 GB blob.
    received = 0
    try:
        with target.open("wb") as fh:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                received += len(chunk)
                if received > _MAX_UPLOAD_BYTES:
                    fh.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"upload exceeds {_MAX_UPLOAD_BYTES} bytes",
                    )
                fh.write(chunk)
    except HTTPException:
        raise
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"upload write failed: {exc}",
        ) from exc

    return {"path": str(target), "name": target.name}
