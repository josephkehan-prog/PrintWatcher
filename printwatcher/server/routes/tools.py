"""Tool dispatch endpoints — runs a ``scripts.<module>`` in a worker thread."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from printwatcher.server.auth import require_token
from printwatcher.server.dto import ToolRunDto, ToolRunStartedDto
from printwatcher.server.state import AppState, get_state
from printwatcher.server.tools import ToolRunner

router = APIRouter(prefix="/api/tools", dependencies=[Depends(require_token)])

_ALLOWED_PREFIXES: tuple[str, ...] = ("scripts.",)


def _is_allowed(module_name: str) -> bool:
    return any(module_name.startswith(p) for p in _ALLOWED_PREFIXES)


def _runner(state: AppState) -> ToolRunner:
    runner: ToolRunner | None = state.extra.get("tool_runner")
    if runner is None:
        runner = ToolRunner(state.events)
        state.extra["tool_runner"] = runner
    return runner


@router.post("/run", response_model=ToolRunStartedDto)
def run_tool(payload: ToolRunDto, state: AppState = Depends(get_state)) -> ToolRunStartedDto:
    if not _is_allowed(payload.module):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"module not allowed: {payload.module}",
        )
    label = payload.label or payload.module.split(".")[-1]
    run_id, _future = _runner(state).submit(payload.module, payload.args, label)
    return ToolRunStartedDto(run_id=run_id, label=label)


@router.post("/{run_id}/cancel")
def cancel_tool(run_id: str, state: AppState = Depends(get_state)) -> dict[str, bool]:
    runner: ToolRunner | None = state.extra.get("tool_runner")
    if runner is None:
        return {"cancelled": False}
    return {"cancelled": runner.cancel(run_id)}
