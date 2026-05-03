using FluentAssertions;
using PrintWatcher.Shell.ViewModels;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class ToolsViewModelTests
{
    [Fact]
    public void DesignTimeConstructor_ProducesEmptyCatalog()
    {
        var vm = new ToolsViewModel();
        vm.Tools.Should().BeEmpty();
    }
}
