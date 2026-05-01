using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using PrintWatcher.Shell.Models;

namespace PrintWatcher.Shell.Services;

/// <summary>Typed wrapper around the FastAPI surface exposed by PrintWatcher-backend.exe.</summary>
public sealed class ApiClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly JsonSerializerOptions _json;

    public ApiClient(Uri baseAddress, string token, HttpMessageHandler? handler = null)
    {
        _http = handler is null ? new HttpClient() : new HttpClient(handler, disposeHandler: true);
        _http.BaseAddress = baseAddress;
        _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        _http.Timeout = TimeSpan.FromSeconds(30);
        _json = new JsonSerializerOptions
        {
            TypeInfoResolver = JsonContext.Default,
        };
    }

    public Uri BaseAddress => _http.BaseAddress!;

    public Task<StateDto?> GetStateAsync(CancellationToken ct = default) =>
        GetAsync<StateDto>("/api/state", ct);

    public Task<PrintOptionsDto?> GetOptionsAsync(CancellationToken ct = default) =>
        GetAsync<PrintOptionsDto>("/api/options", ct);

    public Task<PrintOptionsDto?> PutOptionsAsync(PrintOptionsDto options, CancellationToken ct = default) =>
        PutAsync<PrintOptionsDto, PrintOptionsDto>("/api/options", options, ct);

    public Task<PauseDto?> PostPauseAsync(bool paused, CancellationToken ct = default) =>
        PostAsync<PauseDto, PauseDto>("/api/pause", new PauseDto { Paused = paused }, ct);

    public Task<PrintersDto?> GetPrintersAsync(CancellationToken ct = default) =>
        GetAsync<PrintersDto>("/api/printers", ct);

    public async Task<PrintersDto?> RefreshPrintersAsync(CancellationToken ct = default)
    {
        using var response = await _http.PostAsync("/api/printers/refresh", content: null, ct).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<PrintersDto>(_json, ct).ConfigureAwait(false);
    }

    public async Task<IReadOnlyList<PrintRecordDto>> GetHistoryAsync(
        string? query = null, string? regex = null, int limit = 200, CancellationToken ct = default)
    {
        var url = $"/api/history?limit={limit}";
        if (!string.IsNullOrEmpty(query)) url += $"&q={Uri.EscapeDataString(query)}";
        if (!string.IsNullOrEmpty(regex)) url += $"&regex={Uri.EscapeDataString(regex)}";
        var rows = await GetAsync<IReadOnlyList<PrintRecordDto>>(url, ct).ConfigureAwait(false);
        return rows ?? Array.Empty<PrintRecordDto>();
    }

    public async Task ClearHistoryAsync(CancellationToken ct = default)
    {
        using var response = await _http.DeleteAsync("/api/history", ct).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
    }

    public Task<PreferencesDto?> GetPreferencesAsync(CancellationToken ct = default) =>
        GetAsync<PreferencesDto>("/api/preferences", ct);

    public Task<PreferencesDto?> PutPreferencesAsync(PreferencesDto prefs, CancellationToken ct = default) =>
        PutAsync<PreferencesDto, PreferencesDto>("/api/preferences", prefs, ct);

    public Task<ToolRunStartedDto?> RunToolAsync(
        ToolRunRequestDto request, CancellationToken ct = default) =>
        PostAsync<ToolRunRequestDto, ToolRunStartedDto>("/api/tools/run", request, ct);

    public async Task PostShutdownAsync(CancellationToken ct = default)
    {
        try
        {
            using var response = await _http.PostAsync("/api/shutdown", content: null, ct).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
        }
        catch (HttpRequestException)
        {
            // Backend may have closed the socket before responding. Acceptable on shutdown.
        }
    }

    private async Task<T?> GetAsync<T>(string url, CancellationToken ct)
    {
        using var response = await _http.GetAsync(url, ct).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<T>(_json, ct).ConfigureAwait(false);
    }

    private async Task<TResponse?> PutAsync<TRequest, TResponse>(string url, TRequest body, CancellationToken ct)
    {
        using var response = await _http.PutAsJsonAsync(url, body, _json, ct).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<TResponse>(_json, ct).ConfigureAwait(false);
    }

    private async Task<TResponse?> PostAsync<TRequest, TResponse>(string url, TRequest body, CancellationToken ct)
    {
        using var response = await _http.PostAsJsonAsync(url, body, _json, ct).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<TResponse>(_json, ct).ConfigureAwait(false);
    }

    public void Dispose() => _http.Dispose();
}
