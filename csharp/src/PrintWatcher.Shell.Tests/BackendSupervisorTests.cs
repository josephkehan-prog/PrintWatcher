using System;
using System.Threading.Tasks;
using FluentAssertions;
using PrintWatcher.Shell.Services;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class BackendSupervisorTests
{
    [Fact]
    public void LogTail_EvictsOldestPastCapacity()
    {
        var supervisor = new BackendSupervisor();
        for (var i = 0; i < 2100; i++)
            supervisor.Push($"line {i}");

        var tail = supervisor.LogTail;
        tail.Should().HaveCount(2000);
        tail[^1].Should().Be("line 2099");
        tail[0].Should().Be("line 100");
    }

    [Fact]
    public async Task DevOverride_ParsesUrlAndToken_WithoutSpawning()
    {
        Environment.SetEnvironmentVariable(BackendLocator.DevEnvVar, "http://127.0.0.1:9876;devtoken");
        try
        {
            await using var supervisor = new BackendSupervisor();
            var info = await supervisor.StartAsync(exePath: "ignored").ConfigureAwait(false);
            info.Port.Should().Be(9876);
            info.Token.Should().Be("devtoken");
            info.Pid.Should().Be(0);
            info.BaseAddress.ToString().Should().Be("http://127.0.0.1:9876/");
            info.WebSocketAddress.ToString().Should().Be("ws://127.0.0.1:9876/ws");
        }
        finally
        {
            Environment.SetEnvironmentVariable(BackendLocator.DevEnvVar, null);
        }
    }
}
