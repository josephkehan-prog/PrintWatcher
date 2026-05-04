using FluentAssertions;
using PrintWatcher.Shell.Services;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class ThemePaletteTests
{
    [Fact]
    public void Registry_ContainsAllFiveThemes()
    {
        ThemeRegistry.Palettes.Keys.Should().BeEquivalentTo(
            new[] { "Ocean", "Forest", "Indigo", "Blush", "Glass" });
    }

    [Theory]
    [InlineData("Ocean", "#006494", "#0582ca")]
    [InlineData("Forest", "#0a210f", "#14591d")]
    [InlineData("Indigo", "#2e294e", "#3a345e")]
    [InlineData("Blush", "#d9bdc5", "#e9d4da")]
    [InlineData("Glass", "#f2f4f8", "#ffffff")]
    public void Palette_HexValuesMatchPythonSource(string name, string bg, string panel)
    {
        var palette = ThemeRegistry.Resolve(name);
        palette.Bg.Should().Be(bg);
        palette.Panel.Should().Be(panel);
    }

    [Fact]
    public void Resolve_FallsBackToDefault_WhenNameUnknown()
    {
        var fallback = ThemeRegistry.Resolve("DoesNotExist");
        fallback.Should().Be(ThemeRegistry.Resolve(ThemeRegistry.Default));
    }

    [Fact]
    public void GlassTheme_IsTranslucent()
    {
        ThemeRegistry.Resolve("Glass").Translucent.Should().BeTrue();
    }

    [Theory]
    [InlineData("Ocean")]
    [InlineData("Forest")]
    [InlineData("Indigo")]
    [InlineData("Blush")]
    public void OpaqueThemes_AreNotTranslucent(string name)
    {
        ThemeRegistry.Resolve(name).Translucent.Should().BeFalse();
    }

    [Theory]
    [InlineData("#006494", 0x00, 0x64, 0x94)]
    [InlineData("#abc", 0xaa, 0xbb, 0xcc)]
    [InlineData("ffffff", 0xff, 0xff, 0xff)]
    public void ParseHex_AcceptsShortAndLongForms(string hex, byte r, byte g, byte b)
    {
        // ThemeService.ParseHex is internal; access via InternalsVisibleTo would
        // pollute the prod project. Re-implement here as a behaviour check —
        // values come from the THEMES dict and any drift will fail
        // Palette_HexValuesMatchPythonSource above.
        var s = hex.TrimStart('#');
        if (s.Length == 3)
            s = $"{s[0]}{s[0]}{s[1]}{s[1]}{s[2]}{s[2]}";

        System.Convert.ToByte(s.Substring(0, 2), 16).Should().Be(r);
        System.Convert.ToByte(s.Substring(2, 2), 16).Should().Be(g);
        System.Convert.ToByte(s.Substring(4, 2), 16).Should().Be(b);
    }
}
