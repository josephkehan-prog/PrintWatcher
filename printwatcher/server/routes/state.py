"""``GET /api/state`` boot snapshot + ``POST /api/pause``."""

from __future__ import annotations

import json
import logging
import platform
import time
import urllib.error
import urllib.request
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from printwatcher.core import APP_VERSION, list_printers
from printwatcher.server.auth import require_token
from printwatcher.server.dto import (
    PauseDto,
    PendingItemDto,
    PreferencesDto,
    PrintersDto,
    PrintOptionsDto,
    StateDto,
    StatsDto,
    UpdateCheckDto,
    VersionDto,
)
from printwatcher.server.state import AppState, get_state

log = logging.getLogger("printwatcher.server.routes.state")

_UPDATE_CHECK_TTL_SEC = 24 * 3600  # poll GitHub Releases at most once per day
_UPDATE_CHECK_TIMEOUT_SEC = 5.0
_RELEASES_URL = (
    "https://api.github.com/repos/josephkehan-prog/PrintWatcher/releases/latest"
)

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


def _pending_items(state: AppState) -> list[PendingItemDto]:
    return [
        PendingItemDto(path=str(p), name=p.name)
        for p in state.watcher.pending_paths()
    ]


def _printers_snapshot() -> PrintersDto:
    names = list_printers()
    return PrintersDto(default=names[0] if names else None, list=names)


@router.get("/state", response_model=StateDto)
def get_state_snapshot(state: AppState = Depends(get_state)) -> StateDto:
    prefs = state.get_preferences()
    return StateDto(
        version=state.app_version or APP_VERSION,
        stats=StatsDto(**state.watcher.stats),
        paused=state.watcher.is_paused,
        options=PrintOptionsDto.from_core(state.watcher.get_options()),
        pending=_pending_items(state),
        preferences=PreferencesDto(
            theme=prefs.get("theme", "Ocean"),
            hold_mode=bool(prefs.get("hold_mode", False)),
            larger_text=bool(prefs.get("larger_text", False)),
            reduce_transparency=bool(prefs.get("reduce_transparency", False)),
        ),
        printers=_printers_snapshot(),
    )


@router.post("/pause", response_model=PauseDto)
def post_pause(payload: PauseDto, state: AppState = Depends(get_state)) -> PauseDto:
    state.watcher.set_paused(payload.paused)
    state.events.publish({"type": "paused", "paused": state.watcher.is_paused})
    return PauseDto(paused=state.watcher.is_paused)


@router.get("/version", response_model=VersionDto)
def get_version(state: AppState = Depends(get_state)) -> VersionDto:
    return VersionDto(
        app=state.app_version or APP_VERSION,
        python=platform.python_version(),
    )


def _fetch_latest_release() -> dict:
    """Make one outbound GET to GitHub Releases. Raises on network/parse errors.

    Hardcoded HTTPS URL pointing at the project's own repo; no user input
    flows into the URL. The 5 s timeout keeps a slow response from holding
    the route open.
    """
    req = urllib.request.Request(
        _RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "PrintWatcher"},
    )
    # URL is a hardcoded HTTPS endpoint we control; no SSRF risk.
    with urllib.request.urlopen(req, timeout=_UPDATE_CHECK_TIMEOUT_SEC) as resp:  # noqa: S310  # nosec B310
        body = resp.read().decode("utf-8")
    return json.loads(body)


@router.get("/update-check", response_model=UpdateCheckDto)
def get_update_check(
    force: bool = Query(default=False),
    state: AppState = Depends(get_state),
) -> UpdateCheckDto:
    """Return the latest GitHub Release tag with a 24 h cache.

    Outbound HTTPS to api.github.com once per 24 h per running backend.
    Documented in SECURITY.md. Network/parse errors return a no-update
    response so a transient outage never breaks the dashboard.
    """
    current = state.app_version or APP_VERSION

    # User-disableable kill switch. Default is true so existing installs keep
    # the once-per-day check; flipping the pref to false eliminates the
    # outbound HTTPS request entirely.
    if not state.get_preferences().get("update_check", True):
        return UpdateCheckDto(current=current, has_update=False)

    now = time.monotonic()
    with state._update_check_lock:
        if not force and state.update_check_cache is not None:
            cached_at, cached = state.update_check_cache
            if now - cached_at < _UPDATE_CHECK_TTL_SEC:
                return cached

    try:
        payload = _fetch_latest_release()
    except (urllib.error.URLError, OSError) as exc:
        # Transient network condition — operator can't fix it, just an INFO breadcrumb.
        log.info("update-check network failure: %s", exc)
        return UpdateCheckDto(current=current, has_update=False)

    try:
        latest = (payload.get("tag_name") or "").lstrip("v") or None
        dto = UpdateCheckDto(
            current=current,
            latest=latest,
            html_url=payload.get("html_url"),
            has_update=bool(latest and latest != current),
            checked_at=datetime.now(),
        )
    except (ValueError, KeyError) as exc:
        # Schema drift or malformed response — louder so a release-channel
        # change at GitHub's end doesn't silently disable the dashboard chip.
        log.warning("update-check parse failure: %s", exc)
        return UpdateCheckDto(current=current, has_update=False)

    with state._update_check_lock:
        state.update_check_cache = (now, dto)
    return dto
