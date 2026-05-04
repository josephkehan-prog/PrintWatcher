using System.Collections.Generic;

namespace PrintWatcher.Shell.Services;

/// <summary>One palette's worth of color tokens.</summary>
/// <remarks>
/// Mirrors the Python <c>THEMES</c> dict in <c>printwatcher/core.py</c>. Keep
/// the two in sync; the <c>/api/themes</c> endpoint returns the Python-side
/// dict and the shell's tests assert byte-for-byte parity. The
/// <c>Translucent</c> flag is shell-only — when set, the theme service
/// renders the panel/log-bg surfaces with reduced opacity so the window's
/// acrylic backdrop shows through, and <c>MainWindow</c> swaps in
/// <c>DesktopAcrylicBackdrop</c> instead of Mica.
/// </remarks>
public sealed record ThemePalette(
    string Bg,
    string Panel,
    string LogBg,
    string Text,
    string Muted,
    string Ok,
    string Err,
    string LogText,
    string BtnHover,
    bool Translucent = false);

public static class ThemeRegistry
{
    public const string Default = "Ocean";

    public static readonly IReadOnlyDictionary<string, ThemePalette> Palettes =
        new Dictionary<string, ThemePalette>
        {
            ["Ocean"] = new(
                Bg: "#006494", Panel: "#0582ca", LogBg: "#003e5c",
                Text: "#e0f2ff", Muted: "#a3c4d9",
                Ok: "#00a6fb", Err: "#6b8a9c",
                LogText: "#e0f2ff", BtnHover: "#0a96e0"),

            ["Forest"] = new(
                Bg: "#0a210f", Panel: "#14591d", LogBg: "#04140a",
                Text: "#e1e289", Muted: "#b8b370",
                Ok: "#99aa38", Err: "#acd2ed",
                LogText: "#e1e289", BtnHover: "#1d7028"),

            ["Indigo"] = new(
                Bg: "#2e294e", Panel: "#3a345e", LogBg: "#1f1c36",
                Text: "#f5fbef", Muted: "#9a879d",
                Ok: "#129490", Err: "#7a3b69",
                LogText: "#d4cdd6", BtnHover: "#4a4470"),

            ["Blush"] = new(
                Bg: "#d9bdc5", Panel: "#e9d4da", LogBg: "#fff5f8",
                Text: "#1a3550", Muted: "#5b6976",
                Ok: "#548c2f", Err: "#78c3fb",
                LogText: "#1a3550", BtnHover: "#c9adb5"),

            ["Glass"] = new(
                Bg: "#f2f4f8", Panel: "#ffffff", LogBg: "#fafbfc",
                Text: "#1d1d1f", Muted: "#6e6e73",
                Ok: "#0a84ff", Err: "#ff453a",
                LogText: "#1d1d1f", BtnHover: "#e5e5ea",
                Translucent: true),
        };

    public static ThemePalette Resolve(string name) =>
        Palettes.TryGetValue(name, out var p) ? p : Palettes[Default];
}
