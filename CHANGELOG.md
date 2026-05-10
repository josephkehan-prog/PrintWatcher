# Changelog

All notable changes to PrintWatcher are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- WinUI 3 shell: shared `Styles/Common.xaml` design tokens and a reusable
  `PageHeader` user control across History, Pending, Settings, and Tools.
- WinUI 3 shell: dashboard activity log auto-scrolls and shows an
  empty-state placeholder.
- Backend: `VersionDto` model on `GET /api/version`.
- Backend: `WatcherEventForwarder` class extracted from inline closures.
- Backend: 30 s TTL cache around `list_printers()` (200–500 ms PowerShell
  cold-start was on the `/api/state` hot path).
- Backend: `AppState.get_preferences()` caches the preferences dict; `PUT
  /api/preferences` busts the cache.
- Tray: pause-state sync — `print_watcher_tray.py` POSTs `/api/pause` to
  the running backend on toggle so the WinUI shell stays consistent.
- Tooling: `[tool.ruff]` config; `bandit` clean at medium+ severity.
- Tests: DTO parity test (`tests/test_dto_parity.py`) parses
  `[JsonPropertyName]` keys on the C# shell and asserts the matching
  Pydantic DTO carries every key.
- Tests: regression coverage for three confirmed correctness bugs.
- CI: pytest coverage gating at 65% (baseline 70%); coverage XML uploaded
  as a build artifact.

### Changed
- `print_watcher_tray.py`: `print()` → `logging`; reuses `EXTS` and
  `PRINTED_SUBDIR` from `printwatcher.core`; uses
  `assets/printwatcher.png` as the tray icon (desaturated when paused).
- WinUI 3 shell: `App.xaml` fallback brushes neutralized (ThemeService
  overrides them anyway).

### Fixed
- **`stats['today']` was frozen at startup.** The WatcherCore seeded the
  `today` counter from history once, but no code path incremented it
  afterward. `_dispatch_history` now bumps `today` for successful records
  dated today, and recomputes from history on midnight rollover.
- **`PrinterWorker._inflight` missed unnormalized paths.** Two
  submissions of the same physical file via different `Path`
  representations (watchdog vs rescan poller, double-slash, etc.) could
  evade dedup, risking a duplicate print. `submit()` now resolves to the
  canonical path before dedup.
- **FastAPI lifespan leaked subscribers.** `WatcherEventForwarder.attach`
  was called on every lifespan startup with no detach, so
  `uvicorn --reload` and integration tests doubled, tripled, … event
  fan-out. The forwarder now retains unsubscribe handles and detaches
  in the lifespan `finally` block.

### Deprecated
- `print_watcher_ui.py` (legacy Tk UI) emits a `DeprecationWarning` on
  import and is scheduled for removal in v0.5. The canonical UI is the
  WinUI 3 shell shipped as `PrintWatcher.exe`.

## [0.4.0] - in progress

### Added
- WinUI 3 shell as the canonical desktop UI (`csharp/src/PrintWatcher.Shell/`).
- FastAPI headless backend (`printwatcher.server`) with bearer-token auth
  and a `server.json` discovery file in `%LOCALAPPDATA%/PrintWatcher/`.
- Drag-and-drop file upload on the Dashboard page.
- Per-job print options (printer, copies, sides, color) via
  `OptionsPanel`.
- Hold-mode + Pending page for review-before-print workflows.
- History, Tools, Settings pages.
- Five built-in themes (Ocean, Forest, Indigo, Blush, Glass).
- Multi-binary release: `PrintWatcher.exe` (WinUI shell, self-contained
  win-x64), `PrintWatcher-backend.exe`, `PrintWatcher-cli.exe`,
  `PrintWatcher-legacy.exe` (Tk UI; will be removed in v0.5).

## [0.3.0]

### Added
- Editorial-industrial typography pass; breathing status pip on the
  dashboard.
- CustomTkinter hybrid chrome and "larger text" accessibility toggle.
- Tools menu with in-process runner; Today stat tile; bottom status bar.

## [0.2.0]

### Added
- Tray entrypoint (`print_watcher_tray.py`) with pause/resume.
- Per-machine inbox + SumatraPDF auto-detection.
- iPad workflow documentation (`docs/IPAD_QUICKREF.md`,
  `docs/IPAD_SHORTCUT.md`).

## [0.1.0]

### Added
- Initial release: file watcher + SumatraPDF print pipeline + OneDrive
  inbox convention.
