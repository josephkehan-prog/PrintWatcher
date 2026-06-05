# PR Review: #15 — refactor(shell): centralize design-system styles (type scale + card surface)

**Reviewed**: 2026-06-05
**Author**: self (kbjy9b66jh@privaterelay.appleid.com) — self-authored, so published to GitHub as a COMMENT, not an approval
**Branch**: claude/hopeful-knuth-cUJWS → main
**Decision**: APPROVE with comments (informational COMMENT on GitHub due to self-authorship)

## Summary

Pure XAML style consolidation for the WinUI 3 shell: four duplicated/ inlined style blocks are
lifted into shared keys in `App.xaml` (`PageTitleStyle`, `CaptionLabelStyle`, `MonospaceTextStyle`,
`CardSurfaceStyle`); pages/controls now reference them via `BasedOn` or direct `Style=`, overriding
only what differs. No behavioral or intended visual change. Net −44 lines, one source of truth for
the type scale and card surface.

## Findings

### CRITICAL
None.

### HIGH
None.

### MEDIUM
- **Visual pixel-parity not machine-verified.** The substitutions are value-identical and the XAML
  compiles on the Windows runner, but no screenshot diff was taken (no WinUI runtime in CI/this
  env). Risk is low because the setters are byte-identical to the originals; a human glance on
  Windows is the only remaining confirmation. (Tracked in the PR body.)

### LOW
- **SettingsPage "BACKEND LOG" inset border** keeps its own inline border setters rather than
  deriving from `CardSurfaceStyle`. This is defensible — it is an *inset* log box, not a top-level
  card — so leaving it un-consolidated is reasonable, but it is the one remaining card-like surface
  not pointing at the shared style.
- **Hardcoded sizes** in `CaptionLabelStyle`/`MonospaceTextStyle` (12) and `PageTitleStyle` (32).
  Fine for this PR; these are exactly the levers a future "Larger text" setting would scale, which
  is the stated motivation.

## Parity spot-checks (all pass)
- `PageTitleStyle` ≡ inlined `FontSize=32` / `FontWeight=Light` / `Foreground=TextBrush`.
- `CaptionLabelStyle` ≡ old `StatLabelStyle`/`SectionLabelStyle` (`12` / `CharacterSpacing 80` / `MutedBrush`).
- `MonospaceTextStyle` ≡ inlined `Consolas, Cascadia Code, monospace` / `12` / `LogTextBrush`.
- `CardSurfaceStyle` ≡ old `GroupCardStyle`/`ToolCardStyle`/`StatTileStyle` base (`PanelBrush` /
  `SurfaceBorderBrush` / `1` / `SurfaceShadow` / `16` / `20,16`).
- `StatTileStyle` correctly overrides `CornerRadius` 16→12 and keeps `MinWidth/MinHeight`.
- Log borders override `Padding` (`0`/`16`) and `Background` (`LogBgBrush`) via local values that
  win over the style setters — correct WinUI precedence.
- `GlassDepth.Elevated="True"` left on element instances (attached-property setters in a Style are
  brittle in WinUI) — glass elevation behavior unchanged.
- No dangling `{StaticResource}`: zero references to the three removed keys; all new references
  resolve to the four definitions in `App.xaml`.

## Validation Results

| Check | Result |
|---|---|
| Type check (C#) | Pass (CI: "Test + Build Windows binaries") |
| Lint | N/A |
| Tests (pytest + dotnet) | Pass (CI) |
| Build (WinUI win-x64 publish) | Pass (CI) |
| Dangling StaticResource scan | Pass (manual grep) |

## Files Reviewed
- `csharp/src/PrintWatcher.Shell/App.xaml` — Modified (added 4 shared styles)
- `csharp/src/PrintWatcher.Shell/Controls/OptionsPanel.xaml` — Modified
- `csharp/src/PrintWatcher.Shell/Pages/DashboardPage.xaml` — Modified
- `csharp/src/PrintWatcher.Shell/Pages/HistoryPage.xaml` — Modified
- `csharp/src/PrintWatcher.Shell/Pages/PendingPage.xaml` — Modified
- `csharp/src/PrintWatcher.Shell/Pages/SettingsPage.xaml` — Modified
- `csharp/src/PrintWatcher.Shell/Pages/ToolsPage.xaml` — Modified
