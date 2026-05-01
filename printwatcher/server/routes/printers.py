"""Printer enumeration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from printwatcher.core import list_printers
from printwatcher.server.auth import require_token
from printwatcher.server.dto import PrintersDto

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


def _snapshot() -> PrintersDto:
    names = list_printers()
    return PrintersDto(default=names[0] if names else None, list=names)


@router.get("/printers", response_model=PrintersDto)
def get_printers() -> PrintersDto:
    return _snapshot()


@router.post("/printers/refresh", response_model=PrintersDto)
def refresh_printers() -> PrintersDto:
    return _snapshot()
