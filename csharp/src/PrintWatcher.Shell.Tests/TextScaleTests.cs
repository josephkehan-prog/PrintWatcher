using FluentAssertions;
using PrintWatcher.Shell.Services;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class TextScaleTests
{
    [Fact]
    public void LargerTextOff_ReturnsBaseSizes_Unchanged()
    {
        TextScale.PageTitle(false).Should().Be(TextScale.PageTitleBase);
        TextScale.Caption(false).Should().Be(TextScale.CaptionBase);
        TextScale.Monospace(false).Should().Be(TextScale.MonospaceBase);
    }

    [Fact]
    public void LargerTextOn_ScalesEveryTokenByTheFactor()
    {
        TextScale.PageTitle(true).Should().Be(TextScale.PageTitleBase * TextScale.LargerTextFactor);
        TextScale.Caption(true).Should().Be(TextScale.CaptionBase * TextScale.LargerTextFactor);
        TextScale.Monospace(true).Should().Be(TextScale.MonospaceBase * TextScale.LargerTextFactor);
    }

    [Fact]
    public void LargerTextFactor_IsAModestEnlargement()
    {
        // Big enough to help, small enough not to break layouts. The toggle copy in
        // SettingsPage.xaml advertises "Scaled up by 1.15×", so keep them in step.
        TextScale.LargerTextFactor.Should().BeInRange(1.05, 1.30);
        TextScale.LargerTextFactor.Should().Be(1.15);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Scale_PreservesTokenOrdering(bool largerText)
    {
        // The hierarchy (title > caption) must hold at any scale.
        TextScale.PageTitle(largerText).Should().BeGreaterThan(TextScale.Caption(largerText));
    }

    [Fact]
    public void LargerText_NeverShrinksAToken()
    {
        TextScale.PageTitle(true).Should().BeGreaterThan(TextScale.PageTitle(false));
        TextScale.Caption(true).Should().BeGreaterThan(TextScale.Caption(false));
        TextScale.Monospace(true).Should().BeGreaterThan(TextScale.Monospace(false));
    }

    [Theory]
    [InlineData(10.0)]
    [InlineData(16.0)]
    [InlineData(48.0)]
    public void Scale_AppliesFactorOnlyWhenEnabled(double basePt)
    {
        TextScale.Scale(basePt, largerText: false).Should().Be(basePt);
        TextScale.Scale(basePt, largerText: true).Should().Be(basePt * TextScale.LargerTextFactor);
    }
}
