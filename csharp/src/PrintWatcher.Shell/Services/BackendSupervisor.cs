using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace PrintWatcher.Shell.Services;

public sealed record BackendInfo(int Port, string Token, int Pid)
{
    public Uri BaseAddress => new($"http://127.0.0.1:{Port}/");
    public Uri WebSocketAddress => new($"ws://127.0.0.1:{Port}/ws");
}

/// <summary>
/// Spawns and supervises <c>PrintWatcher-backend.exe</c>. Polls the discovery
/// file the backend writes to <c>%LOCALAPPDATA%/PrintWatcher/server.json</c>
/// to learn which ephemeral port uvicorn picked and the bearer token.
/// </summary>
public sealed class BackendSupervisor : IAsyncDisposable
{
    private const int LogTailCapacity = 2000;
    private readonly object _gate = new();
    private readonly LinkedList<string> _logTail = new();
    private Process? _proc;

    public IReadOnlyList<string> LogTail
    {
        get
        {
            lock (_gate) return _logTail.ToArray();
        }
    }

    public async Task<BackendInfo> StartAsync(string exePath, CancellationToken ct = default)
    {
        // The dev override lets `dotnet run` connect to a uvicorn the user is
        // already running in another terminal — avoids spawning a child.
        var devOverride = Environment.GetEnvironmentVariable(BackendLocator.DevEnvVar);
        if (!string.IsNullOrEmpty(devOverride))
        {
            return ParseDevOverride(devOverride);
        }

        var token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();
        var psi = new ProcessStartInfo(exePath)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        psi.ArgumentList.Add("--port");
        psi.ArgumentList.Add("0");
        psi.ArgumentList.Add("--token");
        psi.ArgumentList.Add(token);

        _proc = Process.Start(psi)
            ?? throw new InvalidOperationException($"Process.Start returned null for {exePath}");
        _proc.OutputDataReceived += (_, e) => Push(e.Data);
        _proc.ErrorDataReceived += (_, e) => Push(e.Data is null ? null : "ERR " + e.Data);
        _proc.BeginOutputReadLine();
        _proc.BeginErrorReadLine();

        var info = await WaitForDiscoveryAsync(_proc.Id, token, ct).ConfigureAwait(false);
        return info;
    }

    private static BackendInfo ParseDevOverride(string raw)
    {
        // Format: "http://127.0.0.1:8765;devtoken"
        var parts = raw.Split(';', 2);
        if (parts.Length != 2)
            throw new FormatException($"PRINTWATCHER_DEV_BACKEND must be 'url;token', got '{raw}'");
        var uri = new Uri(parts[0]);
        return new BackendInfo(uri.Port, parts[1], Pid: 0);
    }

    private async Task<BackendInfo> WaitForDiscoveryAsync(int expectedPid, string expectedToken, CancellationToken ct)
    {
        var path = BackendLocator.ServerJsonPath();
        var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(10);
        while (DateTime.UtcNow < deadline)
        {
            ct.ThrowIfCancellationRequested();
            if (File.Exists(path))
            {
                try
                {
                    var bytes = await File.ReadAllBytesAsync(path, ct).ConfigureAwait(false);
                    using var doc = JsonDocument.Parse(bytes);
                    var pid = doc.RootElement.GetProperty("pid").GetInt32();
                    var port = doc.RootElement.GetProperty("port").GetInt32();
                    var token = doc.RootElement.GetProperty("token").GetString();
                    if (pid == expectedPid && token == expectedToken)
                    {
                        return new BackendInfo(port, expectedToken, pid);
                    }
                }
                catch (JsonException) { /* still being written — retry */ }
                catch (IOException) { /* concurrent write — retry */ }
            }
            await Task.Delay(100, ct).ConfigureAwait(false);
        }
        throw new TimeoutException($"backend never wrote {path} within 10 s");
    }

    public void Push(string? line)
    {
        if (line is null) return;
        lock (_gate)
        {
            _logTail.AddLast(line);
            while (_logTail.Count > LogTailCapacity)
                _logTail.RemoveFirst();
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_proc is null) return;
        try
        {
            if (!_proc.HasExited)
            {
                _proc.Kill(entireProcessTree: true);
                await _proc.WaitForExitAsync().ConfigureAwait(false);
            }
        }
        catch { /* swallow on shutdown */ }
        _proc.Dispose();
        _proc = null;
    }
}
