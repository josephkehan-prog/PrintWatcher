using System.Text.Json;
using FluentAssertions;
using PrintWatcher.Shell.ViewModels;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class ShellViewModelTests
{
    [Fact]
    public void OnFrame_HistoryFrame_RoutesToHistoryViewModel()
    {
        var shell = BuildShell();
        var frame = Parse(@"{""type"":""history"",""record"":{""timestamp"":""2026-05-03"",""filename"":""quiz.pdf"",""status"":""ok"",""submitter"":""Mary""}}");

        shell.OnFrame("history", frame);

        shell.History.Rows.Should().ContainSingle(r => r.Filename == "quiz.pdf");
    }

    [Fact]
    public void OnFrame_PendingFrame_RoutesToPendingViewModel()
    {
        var shell = BuildShell();
        var frame = Parse(@"{""type"":""pending"",""items"":[{""path"":""/in/a"",""name"":""a.pdf""}]}");

        shell.OnFrame("pending", frame);

        shell.Pending.Items.Should().ContainSingle(i => i.Name == "a.pdf");
    }

    [Fact]
    public void OnFrame_StatFrame_RoutesToDashboardViewModel()
    {
        var shell = BuildShell();
        var frame = Parse(@"{""type"":""stat"",""key"":""printed"",""delta"":1,""value"":7}");

        shell.OnFrame("stat", frame);

        shell.Dashboard.Printed.Should().Be(7);
    }

    [Fact]
    public void OnFrame_OptionsFrame_RoutesToOptionsViewModel()
    {
        var shell = BuildShell();
        var frame = Parse(@"{""type"":""options"",""options"":{""printer"":""HP"",""copies"":4,""sides"":""duplex"",""color"":""color""}}");

        shell.OnFrame("options", frame);

        shell.Options.Printer.Should().Be("HP");
        shell.Options.Copies.Should().Be(4);
        shell.Options.Sides.Should().Be("duplex");
        shell.Options.Color.Should().Be("color");
    }

    private static ShellViewModel BuildShell() => new(
        new DashboardViewModel(),
        new HistoryViewModel(),
        new PendingViewModel(),
        new ToolsViewModel(),
        new SettingsViewModel(),
        new OptionsViewModel());

    private static JsonElement Parse(string json)
    {
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement.Clone();
    }
}
