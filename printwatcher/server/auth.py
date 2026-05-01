"""Bearer-token middleware. Token is generated per launch by the WinUI shell.

The shell passes ``--token <hex>`` when spawning the backend; every HTTP
request and the initial WebSocket frame must echo it back. Loopback-only
binding plus the token keeps this surface inaccessible to any other process
on the machine.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from printwatcher.server.state import AppState, get_state

_bearer = HTTPBearer(auto_error=False)


def generate_token() -> str:
    """Return a 32-byte hex token suitable for ``--token`` on launch."""
    return secrets.token_hex(32)


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def require_token(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    state: AppState = Depends(get_state),
) -> None:
    """FastAPI dependency rejecting any request missing or mis-typing the token."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not constant_time_equals(creds.credentials, state.token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
