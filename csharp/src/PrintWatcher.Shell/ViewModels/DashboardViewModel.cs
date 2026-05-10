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

    private int _printed;
    private int _today;
    private int _pending;
    private int _errors;
    private bool _paused;
    private string _statusLabel = "Connecting…";
    private PrintOptionsDto _options = new();
    private InboxHealthDto _inboxHealth = new();

    public DashboardViewModel() { /* design-time + tests */ }

    public DashboardViewModel(ApiClient api)
    {
        _api = api;
        TogglePauseCommand = new AsyncRelayCommand(TogglePauseAsync);
        RefreshInboxHealthCommand = new AsyncRelayCommand(RefreshInboxHealthAsync);
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
    public AsyncRelayCommand? RefreshInboxHealthCommand { get; }

    public InboxHealthDto InboxHealth
    {
        get => _inboxHealth;
        private set => SetField(ref _inboxHealth, value);
    }

    private bool _updateAvailable;
    private string? _updateLatest;
    private string? _updateUrl;

    public bool UpdateAvailable
    {
        get => _updateAvailable;
        private set => SetField(ref _updateAvailable, value);
    }

    public string UpdateLabel => string.IsNullOrEmpty(_updateLatest)
        ? ""
        : $"v{_updateLatest} available";

    public Uri UpdateUrl => new(_updateUrl ?? "https://github.com/josephkehan-prog/PrintWatcher/releases");

    public string InboxBytesLabel => HumanizeBytes(InboxHealth.TotalBytes);

    public string SkippedLabel => $"{InboxHealth.SkippedCount} skipped";

    public bool HasSkipped => InboxHealth.SkippedCount > 0;

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

    public async Task RefreshInboxHealthAsync()
    {
        if (_api is null) return;
        try
        {
            var health = await _api.GetInboxHealthAsync().ConfigureAwait(true);
            if (health is not null)
            {
                InboxHealth = health;
                Raise(nameof(InboxBytesLabel));
                Raise(nameof(SkippedLabel));
                Raise(nameof(HasSkipped));
            }
        }
        catch (Exception ex)
        {
            // Diagnostic only — the tile keeps its previous value rather
            // than blanking. Without this, a backend-down state was
            // indistinguishable from an empty inbox.
            System.Diagnostics.Debug.WriteLine($"[dashboard] inbox-health refresh failed: {ex.Message}");
        }
    }

    public async Task CheckForUpdateAsync()
    {
        if (_api is null) return;
        try
        {
            var info = await _api.GetUpdateCheckAsync().ConfigureAwait(true);
            if (info is null) return;
            _updateLatest = info.Latest;
            _updateUrl = info.HtmlUrl;
            UpdateAvailable = info.HasUpdate;
            Raise(nameof(UpdateLabel));
            Raise(nameof(UpdateUrl));
        }
        catch (Exception ex)
        {
            // A transient network error here shouldn't surface — but the
            // diagnostic distinguishes that from a programming bug (null
            // _api wiring, deserialization failure, etc.).
            System.Diagnostics.Debug.WriteLine($"[dashboard] update-check failed: {ex.Message}");
        }
    }

    private static string HumanizeBytes(long bytes)
    {
        if (bytes < 1024) return $"{bytes} B";
        double value = bytes;
        string[] units = { "KB", "MB", "GB", "TB" };
        var unit = -1;
        do
        {
            value /= 1024;
            unit++;
        } while (value >= 1024 && unit < units.Length - 1);
        return $"{value:F1} {units[unit]}";
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
            case "tool":
                ApplyToolFrame(raw);
                break;
        }
    }

    private void ApplyToolFrame(JsonElement raw)
    {
        // Tool stdout / log lines stream into the activity log so the user
        // can see what a long-running script is doing without a separate
        // dialog. Matches the legacy Tk Tools menu behaviour.
        var stream = raw.TryGetProperty("stream", out var s) ? s.GetString() : null;
        var line = raw.TryGetProperty("line", out var l) ? l.GetString() : null;
        if (stream == "end")
        {
            var rc = raw.TryGetProperty("rc", out var r) ? r.GetInt32() : 0;
            Log.Add(new LogLine("", rc == 0 ? "info" : "error", $"tool finished (rc={rc})"));
        }
        else if (line is not null)
        {
            Log.Add(new LogLine("", stream == "log" ? "info" : "info", line));
        }
        while (Log.Count > LogCapacity)
            Log.RemoveAt(0);
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
