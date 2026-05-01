using System;
using System.Net.WebSockets;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace PrintWatcher.Shell.Services;

public enum ConnState { Connecting, Open, Closed }

/// <summary>
/// Minimal abstraction over <see cref="ClientWebSocket"/> for tests.
/// </summary>
public interface IWebSocketClient : IDisposable
{
    WebSocketState State { get; }
    Task ConnectAsync(Uri uri, CancellationToken ct);
    Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType type, bool endOfMessage, CancellationToken ct);
    Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken ct);
}

internal sealed class ClientWebSocketAdapter : IWebSocketClient
{
    private readonly ClientWebSocket _inner = new();

    public WebSocketState State => _inner.State;

    public Task ConnectAsync(Uri uri, CancellationToken ct) => _inner.ConnectAsync(uri, ct);

    public Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType type, bool endOfMessage, CancellationToken ct) =>
        _inner.SendAsync(buffer, type, endOfMessage, ct);

    public Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken ct) =>
        _inner.ReceiveAsync(buffer, ct);

    public void Dispose() => _inner.Dispose();
}

/// <summary>
/// Single-instance WebSocket client that reconnects with exponential backoff.
/// Frames arrive on the background read loop; UI subscribers should marshal to
/// the dispatcher themselves.
/// </summary>
public sealed class EventStream : IAsyncDisposable
{
    private readonly Uri _uri;
    private readonly string _token;
    private readonly Func<IWebSocketClient> _socketFactory;

    private IWebSocketClient? _ws;
    private CancellationTokenSource? _cts;
    private Task? _runLoop;

    public event Action<string, JsonElement>? FrameReceived;
    public event Action<ConnState>? StateChanged;

    public EventStream(Uri uri, string token, Func<IWebSocketClient>? socketFactory = null)
    {
        _uri = uri;
        _token = token;
        _socketFactory = socketFactory ?? (() => new ClientWebSocketAdapter());
    }

    public ConnState Current { get; private set; } = ConnState.Connecting;

    public Task StartAsync()
    {
        _cts = new CancellationTokenSource();
        _runLoop = Task.Run(() => RunAsync(_cts.Token));
        return Task.CompletedTask;
    }

    private async Task RunAsync(CancellationToken ct)
    {
        var backoff = TimeSpan.FromMilliseconds(250);
        var max = TimeSpan.FromSeconds(8);
        while (!ct.IsCancellationRequested)
        {
            UpdateState(ConnState.Connecting);
            try
            {
                _ws?.Dispose();
                _ws = _socketFactory();
                await _ws.ConnectAsync(_uri, ct).ConfigureAwait(false);
                await SendAuthAsync(_ws, _token, ct).ConfigureAwait(false);
                UpdateState(ConnState.Open);
                backoff = TimeSpan.FromMilliseconds(250);
                await ReadLoopAsync(_ws, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                break;
            }
            catch
            {
                UpdateState(ConnState.Closed);
            }

            if (ct.IsCancellationRequested) break;
            try { await Task.Delay(backoff, ct).ConfigureAwait(false); }
            catch (OperationCanceledException) { break; }
            backoff = TimeSpan.FromMilliseconds(Math.Min(backoff.TotalMilliseconds * 2, max.TotalMilliseconds));
        }
        UpdateState(ConnState.Closed);
    }

    private static async Task SendAuthAsync(IWebSocketClient ws, string token, CancellationToken ct)
    {
        var frame = JsonSerializer.SerializeToUtf8Bytes(new { type = "auth", token });
        await ws.SendAsync(new ArraySegment<byte>(frame), WebSocketMessageType.Text,
            endOfMessage: true, ct).ConfigureAwait(false);
    }

    private async Task ReadLoopAsync(IWebSocketClient ws, CancellationToken ct)
    {
        var buffer = new byte[16 * 1024];
        var assembled = new System.IO.MemoryStream();
        while (ws.State == WebSocketState.Open && !ct.IsCancellationRequested)
        {
            assembled.SetLength(0);
            WebSocketReceiveResult result;
            do
            {
                result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), ct).ConfigureAwait(false);
                if (result.MessageType == WebSocketMessageType.Close) return;
                assembled.Write(buffer, 0, result.Count);
            } while (!result.EndOfMessage);

            var span = assembled.GetBuffer().AsMemory(0, (int)assembled.Length);
            JsonElement element;
            try
            {
                using var doc = JsonDocument.Parse(span);
                element = doc.RootElement.Clone();
            }
            catch (JsonException)
            {
                continue;
            }

            var type = element.TryGetProperty("type", out var t) && t.ValueKind == JsonValueKind.String
                ? t.GetString() ?? ""
                : "";
            FrameReceived?.Invoke(type, element);
        }
    }

    private void UpdateState(ConnState next)
    {
        if (Current == next) return;
        Current = next;
        StateChanged?.Invoke(next);
    }

    public async ValueTask DisposeAsync()
    {
        _cts?.Cancel();
        if (_runLoop is not null)
        {
            try { await _runLoop.ConfigureAwait(false); } catch { /* ignore */ }
        }
        _ws?.Dispose();
        _cts?.Dispose();
    }
}
