using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.Services;

namespace PrintWatcher.Shell.ViewModels;

/// <summary>
/// Bound to <c>SettingsPage</c>. Owns the user-facing preferences:
/// theme picker (5 palettes), accessibility toggles, and the read-only
/// backend log tail.
/// </summary>
public sealed class SettingsViewModel : ObservableObject
{
    private readonly ApiClient? _api;
    private readonly Action<string>? _applyTheme;
    private readonly Func<IReadOnlyList<string>>? _readLogTail;
    private string _selectedTheme = ThemeRegistry.Default;
    private bool _largerText;
    private bool _reduceTransparency;
    private bool _holdMode;
    private string _statusLabel = "";
    private bool _suppressSave;

    public SettingsViewModel() { /* design-time + tests */ }

    public SettingsViewModel(ApiClient api, Action<string> applyTheme, Func<IReadOnlyList<string>> readLogTail)
    {
        _api = api;
        _applyTheme = applyTheme;
        _readLogTail = readLogTail;
        ShowBackendLogCommand = new RelayCommand(LoadLogTail);
    }

    public IReadOnlyList<string> ThemeKeys { get; } = ThemeRegistry.Palettes.Keys.ToArray();

    public string SelectedTheme
    {
        get => _selectedTheme;
        set
        {
            if (!SetField(ref _selectedTheme, value)) return;
            _applyTheme?.Invoke(value);
            _ = SaveAsync();
        }
    }

    public bool LargerText
    {
        get => _largerText;
        set { if (SetField(ref _largerText, value)) _ = SaveAsync(); }
    }

    public bool ReduceTransparency
    {
        get => _reduceTransparency;
        set { if (SetField(ref _reduceTransparency, value)) _ = SaveAsync(); }
    }

    public bool HoldMode
    {
        get => _holdMode;
        set { if (SetField(ref _holdMode, value)) _ = SaveAsync(); }
    }

    public string StatusLabel
    {
        get => _statusLabel;
        private set => SetField(ref _statusLabel, value);
    }

    public IReadOnlyList<string> BackendLog { get; private set; } = Array.Empty<string>();

    private string _logFilter = "";
    private string _logLevel = "Any";  // "Any" | "info" | "warn" | "error"

    public string LogFilter
    {
        get => _logFilter;
        set
        {
            if (SetField(ref _logFilter, value ?? ""))
                Raise(nameof(FilteredLog));
        }
    }

    public string LogLevel
    {
        get => _logLevel;
        set
        {
            if (SetField(ref _logLevel, value ?? "Any"))
                Raise(nameof(FilteredLog));
        }
    }

    public IReadOnlyList<string> LogLevels { get; } = new[] { "Any", "info", "warn", "error" };

    /// <summary>Client-side filter view over <see cref="BackendLog"/>.</summary>
    public IReadOnlyList<string> FilteredLog
    {
        get
        {
            var needle = _logFilter;
            var levelToken = string.Equals(_logLevel, "Any", StringComparison.OrdinalIgnoreCase) ? null : _logLevel;
            if (string.IsNullOrEmpty(needle) && levelToken is null) return BackendLog;

            return BackendLog.Where(line =>
            {
                if (!string.IsNullOrEmpty(needle) && line.IndexOf(needle, StringComparison.OrdinalIgnoreCase) < 0)
                    return false;
                if (levelToken is not null && line.IndexOf(levelToken, StringComparison.OrdinalIgnoreCase) < 0)
                    return false;
                return true;
            }).ToArray();
        }
    }

    public RelayCommand? ShowBackendLogCommand { get; }

    /// <summary>
    /// Seed from the boot snapshot. Suppresses the auto-save side effect so
    /// hydrating the picker doesn't immediately PUT back to the backend.
    /// </summary>
    public void ApplySnapshot(PreferencesDto prefs)
    {
        _suppressSave = true;
        try
        {
            SelectedTheme = prefs.Theme;
            LargerText = prefs.LargerText;
            ReduceTransparency = prefs.ReduceTransparency;
            HoldMode = prefs.HoldMode;
        }
        finally
        {
            _suppressSave = false;
        }
    }

    private void LoadLogTail()
    {
        if (_readLogTail is null) return;
        BackendLog = _readLogTail();
        Raise(nameof(BackendLog));
        Raise(nameof(FilteredLog));
    }

    private async Task SaveAsync()
    {
        if (_api is null || _suppressSave) return;
        try
        {
            await _api.PutPreferencesAsync(new PreferencesDto
            {
                Theme = _selectedTheme,
                LargerText = _largerText,
                ReduceTransparency = _reduceTransparency,
                HoldMode = _holdMode,
            }).ConfigureAwait(true);
            StatusLabel = "Saved.";
        }
        catch (Exception ex)
        {
            StatusLabel = "Error: " + ex.Message;
        }
    }
}
