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

    public event Action<ThemePalette>? ThemeChanged;

    public void Apply(string name)
    {
        var palette = ThemeRegistry.Resolve(name);
        var resources = Application.Current.Resources;

        resources["BgBrush"] = MakeBrush(palette.Bg);
        resources["PanelBrush"] = MakeBrush(palette.Panel, GlassMaterial.PanelAlpha(palette));
        resources["LogBgBrush"] = MakeBrush(palette.LogBg, GlassMaterial.LogBgAlpha(palette));
        resources["TextBrush"] = MakeBrush(palette.Text);
        resources["MutedBrush"] = MakeBrush(palette.Muted);
        resources["OkBrush"] = MakeBrush(palette.Ok);
        resources["ErrBrush"] = MakeBrush(palette.Err);
        resources["LogTextBrush"] = MakeBrush(palette.LogText);
        resources["BtnHoverBrush"] = MakeBrush(palette.BtnHover);

        // Glass depth (shell-only; no Python mirror). Surfaces always carry a 1px
        // border; here we only swap its brush. On solid themes it resolves to a
        // fully transparent stroke (invisible), and on Glass to a bright hairline
        // that defines the frosted pane against the acrylic backdrop. GlassDepth
        // toggles the matching elevation shadow.
        resources["SurfaceBorderBrush"] = MakeBrush(GlassMaterial.GlassBorderHex, GlassMaterial.BorderAlpha(palette));

        // Order matters: publish Current before firing ThemeChanged so any
        // handler that reads back the active theme (e.g. GlassDepth resolving the
        // palette for a freshly hooked surface) sees the new value, not the old.
        Current = name;
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
