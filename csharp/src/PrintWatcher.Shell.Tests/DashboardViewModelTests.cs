using System.Text.Json;
using FluentAssertions;
using PrintWatcher.Shell.ViewModels;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class DashboardViewModelTests
{
    [Fact]
    public void StatFrame_AppliesValueToMatchingProperty()
    {
        var vm = new DashboardViewModel();

        vm.OnFrame("stat", Parse(@"{""key"":""printed"",""delta"":1,""value"":42}"));
        vm.OnFrame("stat", Parse(@"{""key"":""errors"",""delta"":1,""value"":3}"));

        vm.Printed.Should().Be(42);
        vm.Errors.Should().Be(3);
        vm.Today.Should().Be(0);
        vm.Pending.Should().Be(0);
    }

    [Fact]
    public void LogFrame_AppendsToObservableCollection()
    {
        var vm = new DashboardViewModel();

        vm.OnFrame("log", Parse(@"{""ts"":""2026-04-30T10:00"",""level"":""info"",""line"":""hello""}"));
        vm.OnFrame("log", Parse(@"{""ts"":""2026-04-30T10:01"",""level"":""warning"",""line"":""world""}"));

        vm.Log.Should().HaveCount(2);
        vm.Log[0].Line.Should().Be("hello");
        vm.Log[1].Level.Should().Be("warning");
    }

    [Fact]
    public void LogFrame_DropsOldestPastCapacity()
    {
        var vm = new DashboardViewModel();
        for (var i = 0; i < 1100; i++)
            vm.OnFrame("log", Parse(@"{""ts"":""2026"",""level"":""info"",""line"":""line " + i + "\"}"));

        vm.Log.Should().HaveCount(1000);
        vm.Log[0].Line.Should().Be("line 100");
        vm.Log[^1].Line.Should().Be("line 1099");
    }

    [Fact]
    public void HelloFrame_SetsPausedFromServerSnapshot()
    {
        var vm = new DashboardViewModel();
        vm.OnFrame("hello", Parse(@"{""version"":""0.4.0"",""paused"":true}"));
        vm.Paused.Should().BeTrue();
        vm.PauseButtonLabel.Should().Be("Resume");
        vm.StatusLabel.Should().Be("Paused");
    }

    [Fact]
    public void ApplySnapshot_SeedsAllProperties()
    {
        var vm = new DashboardViewModel();
        var snapshot = new Models.StateDto
        {
            Version = "0.4.0",
            Stats = new Models.StatsDto { Printed = 5, Today = 2, Pending = 1, Errors = 0 },
            Paused = false,
            Options = new Models.PrintOptionsDto { Copies = 3, Sides = "duplex" },
        };

        vm.ApplySnapshot(snapshot);

        vm.Printed.Should().Be(5);
        vm.Today.Should().Be(2);
        vm.Options.Copies.Should().Be(3);
        vm.StatusLabel.Should().Be("Watching");
    }

    private static JsonElement Parse(string json)
    {
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement.Clone();
    }
}
