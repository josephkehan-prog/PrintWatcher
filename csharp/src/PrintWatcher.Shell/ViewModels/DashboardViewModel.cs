using System;
using System.Collections.ObjectModel;
using System.Text.Json;
using System.Threading.Tasks;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.Services;

namespace PrintWatcher.Shell.ViewModels;

/// <summary>Bound to <c>DashboardPage</c>.</summary>
public sealed class DashboardViewModel : ObservableObject
{
    private const int LogCapacity = 1000;

    private readonly ApiClient? _api;
    private readonly EventStream? _events;

    private int _printed;
    private int _today;
    private int _pending;
    private int _errors;
    private bool _paused;
    private string _statusLabel = "Connecting…";
    private PrintOptionsDto _options = new();

    public DashboardViewModel() { /* design-time + tests */ }

    public DashboardViewModel(ApiClient api, EventStream events)
    {
        _api = api;
        _events = events;
        _events.FrameReceived += OnFrame;
        TogglePauseCommand = new AsyncRelayCommand(TogglePauseAsync);
    }

    public int Printed { get => _printed; private set => SetField(ref _printed, value); }
    public int Today { get => _today; private set => SetField(ref _today, value); }
    public int Pending { get => _pending; private set => SetField(ref _pending, value); }
    public int Errors { get => _errors; private set => SetField(ref _errors, value); }

    public bool Paused
    {
        get => _paused;
        private set
        {
            if (SetField(ref _paused, value))
            {
                Raise(nameof(StatusLabel));
                Raise(nameof(PauseButtonLabel));
            }
        }
    }

    public string StatusLabel
    {
        get => _paused ? "Paused" : _statusLabel;
        private set => SetField(ref _statusLabel, value);
    }

    public string PauseButtonLabel => _paused ? "Resume" : "Pause";

    public PrintOptionsDto Options
    {
        get => _options;
        private set => SetField(ref _options, value);
    }

    public ObservableCollection<LogLine> Log { get; } = new();
    public AsyncRelayCommand? TogglePauseCommand { get; }

    public void ApplySnapshot(StateDto state)
    {
        Printed = state.Stats.Printed;
        Today = state.Stats.Today;
        Pending = state.Stats.Pending;
        Errors = state.Stats.Errors;
        Paused = state.Paused;
        Options = state.Options;
        StatusLabel = state.Paused ? "Paused" : "Watching";
    }

    private async Task TogglePauseAsync()
    {
        if (_api is null) return;
        var next = !Paused;
        var echo = await _api.PostPauseAsync(next).ConfigureAwait(true);
        if (echo is not null) Paused = echo.Paused;
    }

    /// <summary>
    /// Routes incoming WS frames to the appropriate property mutation. The
    /// EventStream raises this on its read-loop thread; bindings need a
    /// UI-thread marshal in the page (handled there).
    /// </summary>
    public void OnFrame(string type, JsonElement raw)
    {
        switch (type)
        {
            case "stat":
                ApplyStat(raw);
                break;
            case "log":
                ApplyLog(raw);
                break;
            case "paused":
                if (raw.TryGetProperty("paused", out var p) && p.ValueKind is JsonValueKind.True or JsonValueKind.False)
                    Paused = p.GetBoolean();
                break;
            case "hello":
                if (raw.TryGetProperty("paused", out var hp) && hp.ValueKind is JsonValueKind.True or JsonValueKind.False)
                    Paused = hp.GetBoolean();
                break;
            case "options":
                if (raw.TryGetProperty("options", out var optsEl))
                {
                    var opts = optsEl.Deserialize<PrintOptionsDto>(JsonContext.Default.PrintOptionsDto);
                    if (opts is not null) Options = opts;
                }
                break;
        }
    }

    private void ApplyStat(JsonElement raw)
    {
        var key = raw.TryGetProperty("key", out var k) ? k.GetString() : null;
        var value = raw.TryGetProperty("value", out var v) ? v.GetInt32() : 0;
        switch (key)
        {
            case "printed": Printed = value; break;
            case "today": Today = value; break;
            case "pending": Pending = value; break;
            case "errors": Errors = value; break;
        }
    }

    private void ApplyLog(JsonElement raw)
    {
        var line = raw.TryGetProperty("line", out var l) ? l.GetString() : null;
        var level = raw.TryGetProperty("level", out var lv) ? lv.GetString() : "info";
        var ts = raw.TryGetProperty("ts", out var t) ? t.GetString() : "";
        if (line is null) return;
        Log.Add(new LogLine(ts ?? "", level ?? "info", line));
        while (Log.Count > LogCapacity)
            Log.RemoveAt(0);
    }
}

public sealed record LogLine(string Timestamp, string Level, string Line);
