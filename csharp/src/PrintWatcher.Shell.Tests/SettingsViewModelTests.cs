using System.Collections.Generic;
using FluentAssertions;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.ViewModels;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class SettingsViewModelTests
{
    [Fact]
    public void ApplySnapshot_HydratesProperties_WithoutTriggeringSave()
    {
        var themeApplied = new List<string>();
        var vm = new SettingsViewModel(api: null!, themeApplied.Add, () => System.Array.Empty<string>());

        vm.ApplySnapshot(new PreferencesDto
        {
            Theme = "Forest",
            LargerText = true,
            ReduceTransparency = true,
            HoldMode = false,
        });

        vm.SelectedTheme.Should().Be("Forest");
        vm.LargerText.Should().BeTrue();
        vm.ReduceTransparency.Should().BeTrue();
        vm.HoldMode.Should().BeFalse();
        // ApplySnapshot is for hydration; the UI hasn't picked a new theme so
        // the apply callback should still fire (it keeps the brushes in sync).
        themeApplied.Should().Contain("Forest");
    }

    [Fact]
    public void ThemeKeys_ExposesEveryRegisteredPalette()
    {
        var vm = new SettingsViewModel(api: null!, _ => { }, () => System.Array.Empty<string>());
        vm.ThemeKeys.Should().Contain(new[] { "Ocean", "Forest", "Indigo", "Blush", "Glass" });
    }

    [Fact]
    public void ShowBackendLog_PullsFromCallback()
    {
        var tail = new List<string> { "line 1", "line 2" };
        var vm = new SettingsViewModel(api: null!, _ => { }, () => tail);

        vm.BackendLog.Should().BeEmpty();
        vm.ShowBackendLogCommand!.Execute(null);
        vm.BackendLog.Should().BeEquivalentTo(tail);
    }
}
