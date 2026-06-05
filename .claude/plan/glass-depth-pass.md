# Plan: True-glass depth pass (Glass-only)

Selected via /multi-frontend (Claude-solo; Gemini unavailable). Approved scope: all pages.

## Intent
Give glass surfaces depth: lighter translucency (more blur-through), a bright hairline
edge defining each pane against the acrylic, a soft elevation shadow, and an intentional
radius scale. Driven by theme resources -> invisible on opaque themes, consistent across pages.
NO palette hex changes (ThemePaletteTests parity must stay green).

## Files
- NEW Services/GlassMaterial.cs  (pure; testable on CI net8.0 runner)
    PanelAlpha 0.55->0.45, LogBgAlpha 0.40->0.35, BorderAlpha glass 0.6 / opaque 0,
    BorderHex #ffffff, TileRadius 12, SurfaceRadius 16, CastsShadow == Translucent.
- NEW Services/GlassDepth.cs  (WinUI-only) attached property Elevated -> toggles Translation Z
    by App.Current.Theme translucency, re-applies on ThemeChanged.
- NEW Tests/GlassMaterialTests.cs  (pure unit tests)
- EDIT Services/ThemeService.cs  drive alphas from GlassMaterial; publish SurfaceBorderBrush
    + SurfaceBorderThickness resources.
- EDIT App.xaml  fallback SurfaceBorderBrush=Transparent, SurfaceBorderThickness=0, shared ThemeShadow.
- EDIT DashboardPage.xaml, OptionsPanel.xaml, HistoryPage.xaml, PendingPage.xaml,
    ToolsPage.xaml, SettingsPage.xaml  consume border resources + radius scale + GlassDepth.Elevated.
- EDIT Shell.Tests.csproj  add GlassMaterial.cs to <Compile Include>.

## Constraints honored
Palette parity untouched; opaque themes: transparent border / 0 thickness / no Translation -> unchanged.
Universal change: radius 14 -> 12/16 by element role.

## Verification
GlassMaterialTests + ThemePaletteTests run on CI (Linux). WinUI visuals need a Windows build ->
flagged on PR as needing on-device confirmation (no dotnet/WinUI in this sandbox).
