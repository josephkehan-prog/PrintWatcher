namespace PrintWatcher.Shell.Services;

/// <summary>
/// Pure, UI-free type-scale tuning for the "Larger text" accessibility setting.
/// Kept separate from <see cref="ThemeService"/> — which pulls in WinUI types and
/// therefore can't be unit-tested — so the scaling is covered by the
/// cross-compiled <c>net8.0</c> test project, mirroring <see cref="GlassMaterial"/>.
/// </summary>
/// <remarks>
/// These base sizes are the single source of truth for the shared type-scale
/// tokens that <c>App.xaml</c> exposes as <c>FontSize*</c> resources and that
/// <see cref="ThemeService"/> writes (scaled) into <c>Application.Current.Resources</c>.
/// When "Larger text" is off the bases are returned unchanged, so the default
/// rendering is byte-for-byte what the literal values were before.
/// </remarks>
public static class TextScale
{
    /// <summary>Multiplier applied to every token when "Larger text" is on (~15% bump).</summary>
    public const double LargerTextFactor = 1.15;

    /// <summary>Base size of the page title (was the inline <c>FontSize="32"</c>).</summary>
    public const double PageTitleBase = 32;

    /// <summary>Base size of caption / section labels (was the 12px caption style).</summary>
    public const double CaptionBase = 12;

    /// <summary>Base size of monospace log text (was the inline <c>FontSize="12"</c>).</summary>
    public const double MonospaceBase = 12;

    /// <summary>Scale <paramref name="basePt"/> by the larger-text factor when enabled.</summary>
    public static double Scale(double basePt, bool largerText) =>
        largerText ? basePt * LargerTextFactor : basePt;

    /// <summary>Effective page-title size for the current setting.</summary>
    public static double PageTitle(bool largerText) => Scale(PageTitleBase, largerText);

    /// <summary>Effective caption/label size for the current setting.</summary>
    public static double Caption(bool largerText) => Scale(CaptionBase, largerText);

    /// <summary>Effective monospace-log size for the current setting.</summary>
    public static double Monospace(bool largerText) => Scale(MonospaceBase, largerText);
}
