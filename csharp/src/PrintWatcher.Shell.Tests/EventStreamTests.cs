using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.Services;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class EventStreamTests
{
    [Fact]
    public async Task FrameRouting_RaisesEventWithType()
    {
        var stub = new StubSocket();
        stub.Enqueue(@"{""type"":""hello"",""version"":""0.4.0"",""paused"":false}");
        stub.Enqueue(@"{""type"":""stat"",""key"":""printed"",""delta"":1,""value"":42}");
        stub.EnqueueClose();

        await using var stream = new EventStream(
            new Uri("ws://test/"), token: "t", socketFactory: () => stub);

        var received = new BlockingCollection<(string, JsonElement)>();
        stream.FrameReceived += (type, raw) => received.Add((type, raw));

        await stream.StartAsync().ConfigureAwait(false);

        var first = await Task.Run(() => received.Take()).WaitAsync(TimeSpan.FromSeconds(2));
        var second = await Task.Run(() => received.Take()).WaitAsync(TimeSpan.FromSeconds(2));

        first.Item1.Should().Be("hello");
        second.Item1.Should().Be("stat");
        second.Item2.GetProperty("value").GetInt32().Should().Be(42);
    }

    [Fact]
    public void StatFrame_Deserializes()
    {
        const string raw = @"{""type"":""stat"",""key"":""errors"",""delta"":1,""value"":3}";
        var frame = JsonSerializer.Deserialize<StatFrame>(raw, JsonContext.Default.StatFrame);

        frame.Should().NotBeNull();
        frame!.Key.Should().Be("errors");
        frame.Value.Should().Be(3);
    }

    [Fact]
    public void HelloFrame_Deserializes()
    {
        const string raw = @"{""type"":""hello"",""version"":""0.4.0"",""paused"":true}";
        var frame = JsonSerializer.Deserialize<HelloFrame>(raw, JsonContext.Default.HelloFrame);

        frame.Should().NotBeNull();
        frame!.Version.Should().Be("0.4.0");
        frame.Paused.Should().BeTrue();
    }

    private sealed class StubSocket : IWebSocketClient
    {
        private readonly BlockingCollection<byte[]?> _outbox = new();
        private bool _connected;

        public WebSocketState State => _connected ? WebSocketState.Open : WebSocketState.None;

        public void Enqueue(string json) => _outbox.Add(Encoding.UTF8.GetBytes(json));

        public void EnqueueClose() => _outbox.Add(null);

        public Task ConnectAsync(Uri uri, CancellationToken ct)
        {
            _connected = true;
            return Task.CompletedTask;
        }

        public Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType type, bool endOfMessage, CancellationToken ct) =>
            Task.CompletedTask;

        public async Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken ct)
        {
            var item = await Task.Run(() => _outbox.Take(ct), ct).ConfigureAwait(false);
            if (item is null)
            {
                _connected = false;
                return new WebSocketReceiveResult(0, WebSocketMessageType.Close, true);
            }
            var copyLen = Math.Min(item.Length, buffer.Count);
            Buffer.BlockCopy(item, 0, buffer.Array!, buffer.Offset, copyLen);
            return new WebSocketReceiveResult(copyLen, WebSocketMessageType.Text, true);
        }

        public void Dispose() => _outbox.Dispose();
    }
}
