"""Per-printer default options.

Persisted under the ``printer_defaults`` subkey in preferences.json:

    "printer_defaults": {
        "ColorLaser": {"color": "color", "sides": "duplex"},
        "MonoLaser":  {"color": "monochrome"}
    }

The watcher's ``PrinterWorker`` reads this on each job and uses defaults
to fill gaps in the resolved options — explicit ui_options + path-token
overrides always win.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status

from printwatcher.core import save_preferences
from printwatcher.server.auth import require_token
from printwatcher.server.dto import PrintOptionsDto
from printwatcher.server.state import AppState, get_state

router = APIRouter(prefix="/api/printer-defaults", dependencies=[Depends(require_token)])


@router.get("", response_model=dict[str, PrintOptionsDto])
def list_defaults(state: AppState = Depends(get_state)) -> dict[str, PrintOptionsDto]:
    raw = state.get_preferences().get("printer_defaults", {})
    if not isinstance(raw, dict):
        return {}
    return {
        name: PrintOptionsDto(**values) if isinstance(values, dict) else PrintOptionsDto()
        for name, values in raw.items()
    }


@router.get("/{name}", response_model=PrintOptionsDto)
def get_defaults(
    name: str = Path(..., min_length=1, max_length=128),
    state: AppState = Depends(get_state),
) -> PrintOptionsDto:
    raw = state.get_preferences().get("printer_defaults", {})
    entry = raw.get(name) if isinstance(raw, dict) else None
    if not isinstance(entry, dict):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no defaults registered for printer {name!r}",
        )
    return PrintOptionsDto(**entry)


@router.put("/{name}", response_model=PrintOptionsDto)
def put_defaults(
    payload: PrintOptionsDto,
    name: str = Path(..., min_length=1, max_length=128),
    state: AppState = Depends(get_state),
) -> PrintOptionsDto:
    prefs = state.get_preferences()
    defaults = prefs.get("printer_defaults")
    if not isinstance(defaults, dict):
        defaults = {}
    defaults[name] = payload.model_dump(exclude_none=True)
    prefs["printer_defaults"] = defaults
    save_preferences(prefs)
    state.invalidate_preferences(fresh=prefs)
    return payload


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_defaults(
    name: str = Path(..., min_length=1, max_length=128),
    state: AppState = Depends(get_state),
) -> None:
    prefs = state.get_preferences()
    defaults = prefs.get("printer_defaults")
    if not isinstance(defaults, dict) or name not in defaults:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no defaults registered for printer {name!r}",
        )
    defaults.pop(name)
    prefs["printer_defaults"] = defaults
    save_preferences(prefs)
    state.invalidate_preferences(fresh=prefs)
