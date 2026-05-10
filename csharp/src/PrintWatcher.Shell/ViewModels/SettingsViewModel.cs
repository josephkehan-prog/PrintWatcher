using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
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
    private bool _updateCheckEnabled = true;
    private string _statusLabel = "";
    private bool _suppressSave;

    // Per-printer defaults state. `_pdPrinter` is the printer name being
    // edited; the other fields are the editable values. Empty/null means
    // "no override".
    private string? _pdPrinter;
    private string? _pdSides;
    private string? _pdColor;
    private int _pdCopies = 1;

    public SettingsViewModel() { /* design-time + tests */ }

    public SettingsViewModel(ApiClient api, Action<string> applyTheme, Func<IReadOnlyList<string>> readLogTail)
    {
        _api = api;
        _applyTheme = applyTheme;
        _readLogTail = readLogTail;
        ShowBackendLogCommand = new RelayCommand(LoadLogTail);
        SavePrinterDefaultCommand = new AsyncRelayCommand(SavePrinterDefaultAsync);
        ClearPrinterDefaultCommand = new AsyncRelayCommand(ClearPrinterDefaultAsync);
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

    public bool UpdateCheckEnabled
    {
        get => _updateCheckEnabled;
        set { if (SetField(ref _updateCheckEnabled, value)) _ = SaveAsync(); }
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

    public ObservableCollection<string> KnownPrinters { get; } = new();

    public string? PrinterDefaultPrinter
    {
        get => _pdPrinter;
        set
        {
            if (SetField(ref _pdPrinter, value))
                _ = LoadPrinterDefaultAsync();
        }
    }

    public IReadOnlyList<string> SidesOptions { get; } = new[] { "", "simplex", "duplex", "duplexshort" };
    public IReadOnlyList<string> ColorOptions { get; } = new[] { "", "color", "monochrome" };

    public string? PrinterDefaultSides
    {
        get => _pdSides;
        set => SetField(ref _pdSides, value);
    }

    public string? PrinterDefaultColor
    {
        get => _pdColor;
        set => SetField(ref _pdColor, value);
    }

    public int PrinterDefaultCopies
    {
        get => _pdCopies;
        set
        {
            if (SetField(ref _pdCopies, Math.Clamp(value, 1, 99)))
                Raise(nameof(PrinterDefaultCopiesValue));
        }
    }

    /// <summary>NumberBox.Value is typed double — this wrapper bridges to the int property.</summary>
    public double PrinterDefaultCopiesValue
    {
        get => _pdCopies;
        set => PrinterDefaultCopies = (int)Math.Round(value);
    }

    public AsyncRelayCommand? SavePrinterDefaultCommand { get; }
    public AsyncRelayCommand? ClearPrinterDefaultCommand { get; }

    public async Task LoadPrintersAsync()
    {
        if (_api is null) return;
        var p = await _api.GetPrintersAsync().ConfigureAwait(true);
        KnownPrinters.Clear();
        if (p?.List is not null)
            foreach (var name in p.List) KnownPrinters.Add(name);
    }

    private async Task LoadPrinterDefaultAsync()
    {
        if (_api is null || string.IsNullOrEmpty(_pdPrinter)) return;
        try
        {
            var defaults = await _api.ListPrinterDefaultsAsync().ConfigureAwait(true);
            if (defaults is not null && defaults.TryGetValue(_pdPrinter, out var current))
            {
                PrinterDefaultSides = current.Sides ?? "";
                PrinterDefaultColor = current.Color ?? "";
                PrinterDefaultCopies = current.Copies;
            }
            else
            {
                PrinterDefaultSides = "";
                PrinterDefaultColor = "";
                PrinterDefaultCopies = 1;
            }
        }
        catch (Exception ex)
        {
            StatusLabel = "Defaults load failed: " + ex.Message;
        }
    }

    private async Task SavePrinterDefaultAsync()
    {
        if (_api is null || string.IsNullOrEmpty(_pdPrinter)) return;
        var dto = new PrintOptionsDto
        {
            Sides = string.IsNullOrEmpty(_pdSides) ? null : _pdSides,
            Color = string.IsNullOrEmpty(_pdColor) ? null : _pdColor,
            Copies = _pdCopies,
        };
        try
        {
            await _api.PutPrinterDefaultAsync(_pdPrinter, dto).ConfigureAwait(true);
            StatusLabel = $"Defaults saved for {_pdPrinter}.";
        }
        catch (Exception ex)
        {
            StatusLabel = "Defaults save failed: " + ex.Message;
        }
    }

    private async Task ClearPrinterDefaultAsync()
    {
        if (_api is null || string.IsNullOrEmpty(_pdPrinter)) return;
        try
        {
            await _api.DeletePrinterDefaultAsync(_pdPrinter).ConfigureAwait(true);
            PrinterDefaultSides = "";
            PrinterDefaultColor = "";
            PrinterDefaultCopies = 1;
            StatusLabel = $"Defaults cleared for {_pdPrinter}.";
        }
        catch (Exception ex)
        {
            StatusLabel = "Defaults clear failed: " + ex.Message;
        }
    }

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
            UpdateCheckEnabled = prefs.UpdateCheck;
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
                UpdateCheck = _updateCheckEnabled,
            }).ConfigureAwait(true);
            StatusLabel = "Saved.";
        }
        catch (Exception ex)
        {
            StatusLabel = "Error: " + ex.Message;
        }
    }
}
