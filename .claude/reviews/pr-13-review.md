# PR Review: #13 — docs: add CLAUDE.md with architecture and command guidance

**Reviewed**: 2026-06-04
**Author**: (this session)
**Branch**: claude/hopeful-knuth-cUJWS → main
**Decision**: APPROVE (docs-only; one LOW accuracy nit fixed in review)

## Summary
Docs-only change adding `CLAUDE.md`. Review focused on the accuracy of the technical
claims in the doc against the actual code. All load-bearing claims verified correct;
one LOW inaccuracy about `APP_VERSION` sync points was found and corrected.

## Findings

### CRITICAL
None.

### HIGH
None.

### MEDIUM
None.

### LOW
- `CLAUDE.md` originally listed `print_watcher_ui.py` as an `APP_VERSION` sync point.
  In fact `print_watcher_ui.py:54` *imports* `APP_VERSION` from `printwatcher.core`;
  the independent definitions are in `core.py`, `printwatcher_app.py`, and
  `pyproject.toml`. **Fixed** in commit on this branch.

## Claims verified against code
- EventBus thread→asyncio bridge — `printwatcher/server/events.py:54` uses
  `loop.call_soon_threadsafe(self._enqueue, ...)` → `queue.put_nowait`. ✓
- WebSocket auth failure closes with code `4401` — `printwatcher/server/websocket.py:31,36`. ✓
- `PRINTWATCHER_DEV_BACKEND` is `url;token` — `BackendSupervisor.cs:74` splits on `;`. ✓
- Discovery file at `%LOCALAPPDATA%\PrintWatcher\server.json` — `BackendLocator.cs:33`. ✓
- Inbox constants `EXTS`, `STABLE_CHECKS`, `RESERVED_TOP_LEVEL`,
  `FILENAME_OPTIONS_SEPARATOR` — `printwatcher/core.py:32,34,40,57`. ✓

## Validation Results

| Check | Result |
|---|---|
| Type check | Skipped (docs-only) |
| Lint | Skipped (docs-only) |
| Tests | Skipped locally (pytest not installed in container; CI runs full suite on Windows) |
| Build | Skipped (docs-only) |

## Files Reviewed
- `CLAUDE.md` — Added
