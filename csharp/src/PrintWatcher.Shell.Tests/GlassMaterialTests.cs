using FluentAssertions;
using PrintWatcher.Shell.Services;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class GlassMaterialTests
{
    private static readonly string[] OpaqueThemes = { "Ocean", "Forest", "Indigo", "Blush" };

    [Theory]
    [InlineData("Ocean")]
    [InlineData("Forest")]
    [InlineData("Indigo")]
    [InlineData("Blush")]
    public void OpaqueThemes_AreFullyOpaque_AndFlat(string name)
    {
        var palette = ThemeRegistry.Resolve(name);

        GlassMaterial.PanelAlpha(palette).Should().Be(1.0);
        GlassMaterial.LogBgAlpha(palette).Should().Be(1.0);
        GlassMaterial.BorderAlpha(palette).Should().Be(0.0);
        GlassMaterial.ElevationZ(palette).Should().Be(0.0);
        GlassMaterial.CastsShadow(palette).Should().BeFalse();
    }

    [Fact]
    public void Glass_IsTranslucent_Bordered_AndElevated()
    {
        var glass = ThemeRegistry.Resolve("Glass");

        GlassMaterial.PanelAlpha(glass).Should().Be(GlassMaterial.GlassPanelAlpha);
        GlassMaterial.LogBgAlpha(glass).Should().Be(GlassMaterial.GlassLogBgAlpha);
        GlassMaterial.BorderAlpha(glass).Should().BeGreaterThan(0.0);
        GlassMaterial.ElevationZ(glass).Should().BeGreaterThan(0.0);
        GlassMaterial.CastsShadow(glass).Should().BeTrue();
    }

    [Fact]
    public void GlassPanel_IsMoreTransparentThanLegacy()
    {
        // The depth pass lightened the panel fill from the old 0.55 so more of the
        // acrylic backdrop blurs through; the hairline border restores legibility.
        GlassMaterial.GlassPanelAlpha.Should().BeLessThan(0.55);
        GlassMaterial.GlassLogBgAlpha.Should().BeLessThan(GlassMaterial.GlassPanelAlpha);
    }

    [Fact]
    public void TileRadius_IsSmallerThanSurfaceRadius()
    {
        // Intentional radius scale by element role rather than a uniform 14 everywhere.
        GlassMaterial.TileCornerRadius.Should().BeLessThan(GlassMaterial.SurfaceCornerRadius);
    }

    [Fact]
    public void AllAlphas_StayWithinUnitRange()
    {
        foreach (var name in OpaqueThemes)
        {
            var p = ThemeRegistry.Resolve(name);
            GlassMaterial.PanelAlpha(p).Should().BeInRange(0.0, 1.0);
            GlassMaterial.LogBgAlpha(p).Should().BeInRange(0.0, 1.0);
            GlassMaterial.BorderAlpha(p).Should().BeInRange(0.0, 1.0);
        }

        var glass = ThemeRegistry.Resolve("Glass");
        GlassMaterial.PanelAlpha(glass).Should().BeInRange(0.0, 1.0);
        GlassMaterial.LogBgAlpha(glass).Should().BeInRange(0.0, 1.0);
        GlassMaterial.BorderAlpha(glass).Should().BeInRange(0.0, 1.0);
    }
}
