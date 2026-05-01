using System;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.Services;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class ApiClientTests
{
    [Fact]
    public async Task PostPause_RoundTrip_ReturnsServerEcho()
    {
        var handler = new StubHandler((request, ct) =>
        {
            request.Method.Should().Be(HttpMethod.Post);
            request.RequestUri!.AbsolutePath.Should().Be("/api/pause");
            request.Headers.Authorization!.Parameter.Should().Be("test-token");
            return JsonResponse(@"{""paused"": true}");
        });
        using var client = new ApiClient(new Uri("http://localhost:1/"), "test-token", handler);

        var response = await client.PostPauseAsync(true).ConfigureAwait(false);

        response.Should().NotBeNull();
        response!.Paused.Should().BeTrue();
    }

    [Fact]
    public async Task PutOptions_SendsSnakeCase_AndDeserialisesEcho()
    {
        var captured = "";
        var handler = new StubHandler(async (request, ct) =>
        {
            captured = await request.Content!.ReadAsStringAsync(ct).ConfigureAwait(false);
            return JsonResponse(captured);   // server echoes back
        });
        using var client = new ApiClient(new Uri("http://localhost:1/"), "t", handler);

        var sent = new PrintOptionsDto { Printer = "HP", Copies = 3, Sides = "duplex", Color = "color" };
        var got = await client.PutOptionsAsync(sent).ConfigureAwait(false);

        captured.Should().Contain("\"copies\":3").And.Contain("\"sides\":\"duplex\"");
        got.Should().BeEquivalentTo(sent);
    }

    [Fact]
    public async Task GetState_ParsesNestedShape()
    {
        const string body = @"{
            ""version"": ""0.4.0"",
            ""stats"": {""printed"": 7, ""today"": 2, ""pending"": 1, ""errors"": 0},
            ""paused"": false,
            ""options"": {""printer"": null, ""copies"": 1, ""sides"": null, ""color"": null},
            ""pending"": [{""path"": ""/x/a.pdf"", ""name"": ""a.pdf""}],
            ""preferences"": {""theme"": ""Forest"", ""hold_mode"": false, ""larger_text"": false, ""reduce_transparency"": false},
            ""printers"": {""default"": ""HP"", ""list"": [""HP"", ""Canon""]}
        }";
        var handler = new StubHandler((request, ct) => JsonResponse(body));
        using var client = new ApiClient(new Uri("http://localhost:1/"), "t", handler);

        var state = await client.GetStateAsync().ConfigureAwait(false);

        state.Should().NotBeNull();
        state!.Version.Should().Be("0.4.0");
        state.Stats.Printed.Should().Be(7);
        state.Pending.Should().HaveCount(1);
        state.Printers.List.Should().Contain("HP");
        state.Preferences.Theme.Should().Be("Forest");
    }

    private static HttpResponseMessage JsonResponse(string body) =>
        new(HttpStatusCode.OK)
        {
            Content = new StringContent(body, Encoding.UTF8, "application/json"),
        };

    private sealed class StubHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> _impl;

        public StubHandler(Func<HttpRequestMessage, CancellationToken, HttpResponseMessage> impl)
            : this((req, ct) => Task.FromResult(impl(req, ct)))
        { }

        public StubHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> impl)
        {
            _impl = impl;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct) =>
            _impl(request, ct);
    }
}
