using System.IO;
using FluentAssertions;
using PrintWatcher.Shell.Services;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class BackendLocatorTests
{
    [Fact]
    public void ServerJsonPath_IsUnderLocalAppData()
    {
        var path = BackendLocator.ServerJsonPath();
        path.Should().EndWith(Path.Combine("PrintWatcher", "server.json"));
    }

    [Fact]
    public void FindBackend_FallsBackToExecutableName_WhenMissing()
    {
        // No file is staged in the test runner's bin directory, so the locator
        // must return the bare exe name as the last-resort PATH probe.
        var path = BackendLocator.FindBackend();
        Path.GetFileName(path).Should().Be(BackendLocator.ExecutableName);
    }
}
