"""``GET /api/themes`` — read-only THEMES dict for the WinUI shell.

The shell pre-bakes its XAML resource dictionaries from this at build time;
the endpoint exists for diagnostics and dev-mode hot reload.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from printwatcher.core import DEFAULT_THEME, THEMES
from printwatcher.server.auth import require_token

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@router.get("/themes")
def get_themes() -> dict[str, object]:
    return {"default": DEFAULT_THEME, "themes": THEMES}
