using System;
using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using Windows.UI;

namespace PrintWatcher.Shell.Services;

/// <summary>
/// Applies a <see cref="ThemePalette"/> by mutating
/// <c>Application.Current.Resources</c>. Bound brushes pick up the change at
/// the next layout pass; no rebind needed because we use <c>ThemeResource</c>
/// references rather than <c>StaticResource</c>.
/// </summary>
public sealed class ThemeService
{
    public string Current { get; private set; } = ThemeRegistry.Default;

    /// <summary>"Larger text" accessibility setting — scales the shared type tokens.</summary>
    public bool LargerText { get; private set; }

    /// <summary>
    /// "Reduce transparency" accessibility setting — forces opaque/flat surfaces
    /// and a solid window backdrop even under a translucent palette.
    /// </summary>
    public bool ReduceTransparency { get; private set; }

    public event Action<ThemePalette>? ThemeChanged;

    /// <summary>Switch the active theme, keeping the current accessibility flags.</summary>
    public void Apply(string name)
    {
        Current = name;
        Render();
    }

    /// <summary>
    /// Apply theme and both accessibility flags in one render — used at startup so
    /// the persisted preferences land in a single pass before the window appears.
    /// </summary>
    public void Apply(string name, bool largerText, bool reduceTransparency)
    {
        Current = name;
        LargerText = largerText;
        ReduceTransparency = reduceTransparency;
        Render();
    }

    /// <summary>Toggle "Larger text" and re-render (no-op if unchanged).</summary>
    public void SetLargerText(bool on)
    {
        if (LargerText == on) return;
        LargerText = on;
        Render();
    }

    /// <summary>Toggle "Reduce transparency" and re-render (no-op if unchanged).</summary>
    public void SetReduceTransparency(bool on)
    {
        if (ReduceTransparency == on) return;
        ReduceTransparency = on;
        Render();
    }

    private void Render()
    {
        var palette = ThemeRegistry.Resolve(Current);
        var resources = Application.Current.Resources;

        resources["BgBrush"] = MakeBrush(palette.Bg);
        resources["PanelBrush"] = MakeBrush(palette.Panel, GlassMaterial.PanelAlpha(palette, ReduceTransparency));
        resources["LogBgBrush"] = MakeBrush(palette.LogBg, GlassMaterial.LogBgAlpha(palette, ReduceTransparency));
        resources["TextBrush"] = MakeBrush(palette.Text);
        resources["MutedBrush"] = MakeBrush(palette.Muted);
        resources["OkBrush"] = MakeBrush(palette.Ok);
        resources["ErrBrush"] = MakeBrush(palette.Err);
        resources["LogTextBrush"] = MakeBrush(palette.LogText);
        resources["BtnHoverBrush"] = MakeBrush(palette.BtnHover);

        // Glass depth (shell-only; no Python mirror). Surfaces always carry a 1px
        // border; here we only swap its brush. On solid themes — and whenever
        // "Reduce transparency" is on — it resolves to a fully transparent stroke
        // (invisible); on Glass to a bright hairline that defines the frosted pane
        // against the acrylic backdrop. GlassDepth toggles the matching shadow.
        resources["SurfaceBorderBrush"] =
            MakeBrush(GlassMaterial.GlassBorderHex, GlassMaterial.BorderAlpha(palette, ReduceTransparency));

        // Type scale: the three shared FontSize* tokens (referenced by the App.xaml
        // styles via ThemeResource) are written here scaled by the "Larger text"
        // setting, so one Render keeps colour and typography in sync.
        resources["FontSizePageTitle"] = TextScale.PageTitle(LargerText);
        resources["FontSizeCaption"] = TextScale.Caption(LargerText);
        resources["FontSizeMonospace"] = TextScale.Monospace(LargerText);

        // ThemeChanged fires last so handlers that read back the flags / Current
        // (MainWindow backdrop, GlassDepth elevation) see the new state.
        ThemeChanged?.Invoke(palette);
    }

    private static SolidColorBrush MakeBrush(string hex, double alpha = 1.0)
    {
        var color = ParseHex(hex);
        if (alpha < 1.0)
            color = Color.FromArgb((byte)Math.Round(255 * Math.Clamp(alpha, 0.0, 1.0)), color.R, color.G, color.B);
        return new SolidColorBrush(color);
    }

    internal static Color ParseHex(string hex)
    {
        var s = hex.TrimStart('#');
        if (s.Length == 3)
            s = $"{s[0]}{s[0]}{s[1]}{s[1]}{s[2]}{s[2]}";
        if (s.Length != 6)
            throw new FormatException($"expected #rrggbb, got '{hex}'");
        var r = Convert.ToByte(s.Substring(0, 2), 16);
        var g = Convert.ToByte(s.Substring(2, 2), 16);
        var b = Convert.ToByte(s.Substring(4, 2), 16);
        return Color.FromArgb(0xFF, r, g, b);
    }
}
