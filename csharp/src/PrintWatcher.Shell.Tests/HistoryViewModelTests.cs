using FluentAssertions;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.ViewModels;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class HistoryViewModelTests
{
    [Fact]
    public void OnHistoryFrame_PrependsRecord()
    {
        var vm = new HistoryViewModel();
        var first = new PrintRecordDto { Filename = "first.pdf" };
        var second = new PrintRecordDto { Filename = "second.pdf" };

        vm.OnHistoryFrame(first);
        vm.OnHistoryFrame(second);

        vm.Rows.Should().HaveCount(2);
        vm.Rows[0].Filename.Should().Be("second.pdf");
        vm.Rows[1].Filename.Should().Be("first.pdf");
    }
}
