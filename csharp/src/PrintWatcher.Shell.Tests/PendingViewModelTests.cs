using System.Collections.Generic;
using FluentAssertions;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.ViewModels;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class PendingViewModelTests
{
    [Fact]
    public void OnPendingFrame_ReplacesItems()
    {
        var vm = new PendingViewModel();
        vm.Items.Add(new PendingItemDto { Path = "stale", Name = "stale.pdf" });

        vm.OnPendingFrame(new List<PendingItemDto>
        {
            new() { Path = "/in/a.pdf", Name = "a.pdf" },
            new() { Path = "/in/b.pdf", Name = "b.pdf" },
        });

        vm.Items.Should().HaveCount(2);
        vm.Items[0].Name.Should().Be("a.pdf");
        vm.IsEmpty.Should().BeFalse();
    }

    [Fact]
    public void EmptyFrame_LeavesIsEmptyTrue()
    {
        var vm = new PendingViewModel();
        vm.OnPendingFrame(new List<PendingItemDto>());

        vm.Items.Should().BeEmpty();
        vm.IsEmpty.Should().BeTrue();
    }
}
