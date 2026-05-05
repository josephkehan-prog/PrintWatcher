# Implementation Plan: UI Cleanup (WinUI Shell + FastAPI Backend + Tray)

## Scope

In-scope surfaces:
- `csharp/src/PrintWatcher.Shell/` — WinUI 3 shell (Pages, ViewModels, Services, Controls, Themes)
- `printwatcher/server/` — FastAPI backend that powers the shell
- `print_watcher_tray.py` — minimal tray-only entrypoint

Off-limits: `print_watcher_ui.py` (legacy Tk UI, ~83KB) — do not touch.

### Task Type
- [x] Frontend (WinUI shell, tray)
- [x] Backend (FastAPI server)
- [x] Fullstack — three coordinated, mostly independent surfaces

---

## Findings (current state)

### WinUI Shell (`csharp/src/PrintWatcher.Shell/`)
- 5 pages (`Dashboard`, `History`, `Pending`, `Tools`, `Settings`) all duplicate two near-identical local styles (`SectionLabelStyle`, a card border style). No shared `Styles.xaml`.
- Page-level chrome is hand-rolled per page: every page repeats `Padding="32,24,32,32"`, a `FontSize=32 FontWeight=Light` title, and a status sub-label. No `PageHeader` user control.
- `App.xaml` declares fallback brushes inline with hardcoded Ocean colors and a wall-of-text comment (`App.xaml:12-23`). `ThemeService` overrides them at runtime, so the fallbacks are largely dead weight.
- Card radii (14), label letter-spacing (80), and label colors (`MutedBrush`) are scattered as magic numbers across at least 4 XAML files.
- Activity log uses a `ListView` inside a fixed-height `Border` (`DashboardPage.xaml:85-126`); no auto-scroll, no empty state, FontFamily duplicated in two places.
- `Pages/HistoryPage.xaml`, `PendingPage.xaml`, `SettingsPage.xaml`, `ToolsPage.xaml` each declare their own `SectionLabelStyle` — copy/paste drift risk.
- `MainWindow.xaml`'s `TitleBarRightInset` is hardcoded `Width="148"` — should follow system caption-button metrics, not a magic constant.
- ViewModels under `ViewModels/` largely fine but `OptionsViewModel.cs` (149 lines) and `DashboardViewModel.cs` (168 lines) are the two largest — candidates for trimming any dead helpers.

### FastAPI Backend (`printwatcher/server/`)
- 12 route modules totaling 1,233 lines. Generally healthy and small (`< 200 LOC` each), but:
  - `state.py:62-68` does an in-function `import platform` — should be top-level.
  - `app.py:21-47` builds four nested closures inside `_wire_subscriptions` — can be flattened or moved into a class for testability.
  - DTOs in `dto.py` (106 lines) and routes share string keys with the shell `JsonContext.cs`. Worth verifying naming parity and moving any duplicated literals to constants on the Python side.
  - `routes/__init__.py` likely re-exports `ALL_ROUTERS` — confirm no orphaned imports.
  - No unified error-response schema; some endpoints return `dict[str, str]` ad-hoc (`state.py:62`).
- `print_watcher_tray.py` uses `print()` — should use `logging` per Python style rules.

### Tray (`print_watcher_tray.py`, 109 lines)
- Hardcoded paths (`WATCH_DIR`, `SUMATRA`) at module top — should come from env / `printwatcher.core.load_preferences()`.
- `print()` statements (5×) — switch to `logging`.
- Reimplements `wait_until_stable` and printing logic that already exists in `printwatcher.core.WatcherCore`. Should delegate, not duplicate.
- `make_icon` builds icons procedurally instead of reusing `assets/printwatcher.png`.
- Pause state is module-global (`paused = threading.Event()`) — fine for now, but couple it with the backend's `is_paused` so tray + shell agree.

---

## Technical Solution

Three independent tracks. Each track is mergeable on its own; do them in this order to keep PRs small.

**Track A — WinUI shell visual + structural cleanup** (lowest risk, highest visible impact)
1. Extract one shared `Styles/Common.xaml` ResourceDictionary with `SectionLabelStyle`, `GroupCardStyle`, `StatTileStyle`, `SectionTitleStyle`, and named constants (`CardCornerRadius=14`, `LabelLetterSpacing=80`, `PageContentPadding`).
2. Wire it into `App.xaml` via `MergedDictionaries` and delete the per-page duplicates.
3. Add a `Controls/PageHeader.xaml` user control taking `Title` + `Subtitle` deps; replace the 5 hand-rolled headers.
4. Remove dead Ocean-color fallback brushes from `App.xaml` (ThemeService always overrides). Keep one neutral fallback only to avoid designer flash.
5. Replace `TitleBarRightInset Width="148"` with `CoreApplicationViewTitleBar.SystemOverlayRightInset` binding (or document why the constant is needed in one short comment).
6. Dashboard activity log: add auto-scroll-to-end and an empty-state message; consolidate the two `FontFamily` declarations into a `Style x:Key="LogTextStyle"`.
7. Trim unused `using` directives and run `dotnet format` over the whole project.

**Track B — FastAPI backend cleanup** (small, mechanical)
1. Move all in-function imports to module top.
2. Refactor `_wire_subscriptions` in `app.py` from four closures into a small `WatcherEventForwarder` class (still no behavior change, but unit-testable).
3. Standardize a `VersionDto` / `ErrorDto` so `GET /api/version` and any future error path use Pydantic models, not raw dicts.
4. Audit `routes/*.py` for unused imports / unreachable branches; run `ruff check` and `bandit -r printwatcher/server` (introduce a `[tool.ruff]` block to `pyproject.toml`).
5. Confirm DTO field names match the C# `JsonContext.cs` source-generation set; add a one-shot test that loads each DTO and serializes against the shell's expected keys.

**Track C — Tray cleanup** (small but breaks behavior if rushed — do behind a flag if needed)
1. Replace hardcoded `WATCH_DIR`, `SUMATRA`, `EXTS` with values from `printwatcher.core` (`load_preferences()`, watched-extension constants).
2. Replace `print()` with a module logger (`log = logging.getLogger("printwatcher.tray")`).
3. Delegate file-stable detection and print invocation to `printwatcher.core.WatcherCore.print_path()` (or whatever the equivalent public method is — confirm during implementation). Tray becomes a thin watcher + icon adapter only.
4. Use `assets/printwatcher.png` (recolored for paused state) instead of drawing the icon by hand.
5. Sync pause toggle with backend if the backend is running (HTTP `POST /api/pause`); fall back to local `paused` event if no backend reachable.

---

## Implementation Steps

| # | Step | Track | Expected deliverable |
|---|------|-------|----------------------|
| 1 | Create `Styles/Common.xaml`, register in `App.xaml` | A | Shared resource dictionary, app builds |
| 2 | Add `Controls/PageHeader.xaml(.cs)` with `Title`/`Subtitle` DPs | A | New UC, builds |
| 3 | Replace headers in 5 pages with `<controls:PageHeader …/>` | A | Pages render same as before, `dotnet test` green |
| 4 | Delete duplicate `SectionLabelStyle` / card styles from each page | A | Pages still render |
| 5 | Replace `TitleBarRightInset` constant with system inset binding (or document) | A | Caption buttons clickable on all DPI scales |
| 6 | Polish dashboard log (auto-scroll + empty state + shared style) | A | Visual sanity check |
| 7 | Trim `App.xaml` brushes; `dotnet format` whole shell project | A | Clean diff, build green |
| 8 | Move backend in-function imports to top; add `VersionDto` | B | `pytest` green, `/api/version` returns model |
| 9 | Refactor `_wire_subscriptions` into `WatcherEventForwarder` class | B | Existing tests pass; add a unit test |
| 10 | Add ruff config to `pyproject.toml`; run `ruff check --fix`; add CI step | B | Lint clean |
| 11 | Add DTO ↔ shell-key parity test | B | New test passes |
| 12 | Tray: swap `print()` → `logging`, hardcoded paths → `load_preferences()` | C | Tray still functional locally |
| 13 | Tray: delegate print logic to `WatcherCore`; remove duplicated stable-wait | C | One implementation, not two |
| 14 | Tray: load `assets/printwatcher.png`; tint for paused state | C | Branded icon |
| 15 | Tray: optional `POST /api/pause` sync when backend reachable | C | Pause state coherent across surfaces |

---

## Key Files

| File | Operation | Description |
|------|-----------|-------------|
| `csharp/src/PrintWatcher.Shell/Styles/Common.xaml` | Add | Shared styles + design-token resources |
| `csharp/src/PrintWatcher.Shell/App.xaml` | Modify | Merge `Common.xaml`, drop fallback brush wall |
| `csharp/src/PrintWatcher.Shell/Controls/PageHeader.xaml{,.cs}` | Add | Reusable title+subtitle header |
| `csharp/src/PrintWatcher.Shell/Pages/DashboardPage.xaml` | Modify | Use `PageHeader`, shared styles, polished log |
| `csharp/src/PrintWatcher.Shell/Pages/HistoryPage.xaml` | Modify | Use `PageHeader`, shared styles |
| `csharp/src/PrintWatcher.Shell/Pages/PendingPage.xaml` | Modify | Use `PageHeader`, shared styles |
| `csharp/src/PrintWatcher.Shell/Pages/SettingsPage.xaml` | Modify | Use `PageHeader`, shared styles |
| `csharp/src/PrintWatcher.Shell/Pages/ToolsPage.xaml` | Modify | Use `PageHeader`, shared styles |
| `csharp/src/PrintWatcher.Shell/MainWindow.xaml{,.cs}` | Modify | Replace magic title-bar inset |
| `printwatcher/server/app.py` | Modify | Extract `WatcherEventForwarder` |
| `printwatcher/server/routes/state.py` | Modify | Top-level `import platform`, return `VersionDto` |
| `printwatcher/server/dto.py` | Modify | Add `VersionDto`, `ErrorDto`, audit field names |
| `pyproject.toml` | Modify | Add `[tool.ruff]` config |
| `tests/test_dto_parity.py` | Add | Parity test against shell JSON keys |
| `print_watcher_tray.py` | Modify | logging, prefs, delegate to `WatcherCore`, real icon, optional API sync |
| `assets/` | (read only) | Reuse existing PNG/ICO |

---

## Risks and Mitigation

| Risk | Mitigation |
|------|------------|
| Style refactor changes pixel layout subtly | Take before/after screenshots of each page on a Win11 VM; keep PR per-page if needed |
| Removing `App.xaml` fallback brushes causes designer flash with no theme | Keep one neutral fallback (panel + text) — only delete the redundant 9-color block |
| `WatcherEventForwarder` extraction shifts subscription order | Keep the public `_wire_subscriptions(watcher, events)` function as a thin wrapper that constructs the class |
| Tray delegation to `WatcherCore` may pull GUI-only deps into tray binary | Confirm `WatcherCore` has no `tkinter`/`customtkinter` import; if it does, gate the import or split a `core.printing` module |
| Ruff finds many existing issues | First PR adds the config in non-blocking mode; second PR fixes findings |
| DTO parity test is too brittle | Compare only field names + types, not docstrings; allow extra fields on either side initially |

---

## Validation per track

- **A (shell)**: `cd csharp && dotnet build PrintWatcher.sln -c Release` + `dotnet test src/PrintWatcher.Shell.Tests/`. Visual smoke test on each of the 5 pages.
- **B (backend)**: `pytest -q`, `ruff check printwatcher/`, `bandit -r printwatcher/server`.
- **C (tray)**: Manual run on Windows: drop a sample PDF, observe log output, toggle pause, quit. Confirm the backend's `/api/state` reflects pause state when running together.

---

## SESSION_ID (for /ccg:execute use)

- CODEX_SESSION: (multi-model wrapper not available in this environment — Claude-only plan)
- GEMINI_SESSION: (n/a)

---

**Plan generated and saved to `.claude/plan/ui-cleanup.md`**

**Please review the plan above. You can:**
- **Modify plan**: Tell me what needs adjustment, I'll update the plan
- **Execute plan**: Copy the following command to a new session

```
/ccg:execute .claude/plan/ui-cleanup.md
```
