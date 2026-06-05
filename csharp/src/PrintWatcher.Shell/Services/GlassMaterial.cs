namespace PrintWatcher.Shell.Services;

/// <summary>
/// Pure, UI-free description of the "glass" depth treatment applied to
/// translucent palettes. Kept separate from <see cref="ThemeService"/> — which
/// pulls in WinUI types and therefore can't be unit-tested — so the tuning is
/// covered by the cross-compiled <c>net8.0</c> test project.
/// </summary>
/// <remarks>
/// Opaque palettes resolve to a no-op: full surface alpha, zero border alpha,
/// zero elevation. The four solid (Mica) themes therefore render exactly as
/// before. Only the Glass palette (<see cref="ThemePalette.Translucent"/>)
/// picks up the lighter fill, the bright hairline edge, and the lift.
/// </remarks>
public static class GlassMaterial
{
    /// <summary>Surface fill alpha for solid (Mica) palettes.</summary>
    public const double OpaqueAlpha = 1.0;

    /// <summary>
    /// Panel fill alpha on glass — lighter than the previous 0.55 so more of the
    /// acrylic backdrop blurs through. Legibility is held by the hairline border.
    /// </summary>
    public const double GlassPanelAlpha = 0.45;

    /// <summary>Recessed-surface (log/list) fill alpha on glass (was 0.40).</summary>
    public const double GlassLogBgAlpha = 0.35;

    /// <summary>Alpha of the bright hairline edge that defines a glass pane against the backdrop.</summary>
    public const double GlassBorderAlpha = 0.60;

    /// <summary>Hairline edge colour — white reads as a lit top edge on the light Glass palette.</summary>
    public const string GlassBorderHex = "#ffffff";

    /// <summary>Corner radius for small surfaces (stat tiles).</summary>
    public const double TileCornerRadius = 12;

    /// <summary>Corner radius for large surfaces (panels, logs, cards).</summary>
    public const double SurfaceCornerRadius = 16;

    /// <summary>Shadow lift (Translation Z) applied to elevated glass surfaces; 0 = no cast.</summary>
    public const double GlassElevationZ = 28;

    /// <summary>Fill alpha for the primary (panel) surface of <paramref name="palette"/>.</summary>
    public static double PanelAlpha(ThemePalette palette) =>
        palette.Translucent ? GlassPanelAlpha : OpaqueAlpha;

    /// <summary>Fill alpha for the recessed (log/list) surface of <paramref name="palette"/>.</summary>
    public static double LogBgAlpha(ThemePalette palette) =>
        palette.Translucent ? GlassLogBgAlpha : OpaqueAlpha;

    /// <summary>
    /// Border alpha for <paramref name="palette"/>: a visible hairline on glass,
    /// fully transparent on solid themes (so they keep their borderless look).
    /// </summary>
    public static double BorderAlpha(ThemePalette palette) =>
        palette.Translucent ? GlassBorderAlpha : 0.0;

    /// <summary>
    /// Elevation (Translation Z) for <paramref name="palette"/>: lifted on glass,
    /// flat on solid themes so no shadow is cast.
    /// </summary>
    public static double ElevationZ(ThemePalette palette) =>
        palette.Translucent ? GlassElevationZ : 0.0;

    /// <summary>Whether surfaces should cast an elevation shadow under <paramref name="palette"/>.</summary>
    public static bool CastsShadow(ThemePalette palette) => palette.Translucent;
}
