using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.Services;

namespace PrintWatcher.Shell.ViewModels;

/// <summary>
/// Bound to <c>HistoryPage</c>. Loads on first navigation, refreshes on
/// "history" WS frames, supports a substring/regex filter and a clear-all
/// command.
/// </summary>
public sealed class HistoryViewModel : ObservableObject
{
    private readonly ApiClient? _api;
    private string _filter = "";
    private string _statusLabel = "";
    private bool _useRegex;

    public HistoryViewModel() { /* design-time + tests */ }

    public HistoryViewModel(ApiClient api)
    {
        _api = api;
        RefreshCommand = new AsyncRelayCommand(RefreshAsync);
        ClearCommand = new AsyncRelayCommand(ClearAsync);
    }

    public ObservableCollection<PrintRecordDto> Rows { get; } = new();

    public string Filter
    {
        get => _filter;
        set
        {
            if (SetField(ref _filter, value ?? ""))
                _ = RefreshAsync();
        }
    }

    public bool UseRegex
    {
        get => _useRegex;
        set
        {
            if (SetField(ref _useRegex, value))
                _ = RefreshAsync();
        }
    }

    public string StatusLabel
    {
        get => _statusLabel;
        private set => SetField(ref _statusLabel, value);
    }

    public AsyncRelayCommand? RefreshCommand { get; }
    public AsyncRelayCommand? ClearCommand { get; }

    public async Task RefreshAsync()
    {
        if (_api is null) return;
        var query = _useRegex ? null : (string.IsNullOrWhiteSpace(_filter) ? null : _filter);
        var regex = _useRegex && !string.IsNullOrWhiteSpace(_filter) ? _filter : null;
        try
        {
            var rows = await _api.GetHistoryAsync(query, regex).ConfigureAwait(true);
            Rows.Clear();
            foreach (var row in rows) Rows.Add(row);
            StatusLabel = rows.Count == 0
                ? "No prints match this filter."
                : $"{rows.Count} record{(rows.Count == 1 ? "" : "s")}";
        }
        catch (Exception ex)
        {
            StatusLabel = "Error: " + ex.Message;
        }
    }

    private async Task ClearAsync()
    {
        if (_api is null) return;
        try
        {
            await _api.ClearHistoryAsync().ConfigureAwait(true);
            Rows.Clear();
            StatusLabel = "History cleared.";
        }
        catch (Exception ex)
        {
            StatusLabel = "Error: " + ex.Message;
        }
    }

    /// <summary>
    /// Append a single record received via the "history" WS frame. The
    /// backend already filters server-side, so we just prepend to keep the
    /// most recent print on top.
    /// </summary>
    public void OnHistoryFrame(PrintRecordDto record) => Rows.Insert(0, record);
}
