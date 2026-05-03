using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.Services;

namespace PrintWatcher.Shell.ViewModels;

/// <summary>
/// Bound to <c>PendingPage</c>. Reflects the hold-and-release queue —
/// release prints everything, skip moves them to <c>_skipped/</c>.
/// </summary>
public sealed class PendingViewModel : ObservableObject
{
    private readonly ApiClient? _api;
    private string _statusLabel = "";

    public PendingViewModel() { /* design-time + tests */ }

    public PendingViewModel(ApiClient api)
    {
        _api = api;
        RefreshCommand = new AsyncRelayCommand(RefreshAsync);
        PrintAllCommand = new AsyncRelayCommand(PrintAllAsync, () => Items.Count > 0);
        SkipAllCommand = new AsyncRelayCommand(SkipAllAsync, () => Items.Count > 0);
        Items.CollectionChanged += (_, _) =>
        {
            PrintAllCommand?.NotifyCanExecuteChanged();
            SkipAllCommand?.NotifyCanExecuteChanged();
            Raise(nameof(IsEmpty));
        };
    }

    public ObservableCollection<PendingItemDto> Items { get; } = new();

    public bool IsEmpty => Items.Count == 0;

    public string StatusLabel
    {
        get => _statusLabel;
        private set => SetField(ref _statusLabel, value);
    }

    public AsyncRelayCommand? RefreshCommand { get; }
    public AsyncRelayCommand? PrintAllCommand { get; }
    public AsyncRelayCommand? SkipAllCommand { get; }

    public async Task RefreshAsync()
    {
        if (_api is null) return;
        try
        {
            var items = await _api.GetPendingAsync().ConfigureAwait(true);
            Replace(items);
            StatusLabel = "";
        }
        catch (Exception ex)
        {
            StatusLabel = "Error: " + ex.Message;
        }
    }

    private async Task PrintAllAsync()
    {
        if (_api is null) return;
        try
        {
            await _api.PrintPendingAsync().ConfigureAwait(true);
            StatusLabel = "Released — printing in progress.";
        }
        catch (Exception ex)
        {
            StatusLabel = "Error: " + ex.Message;
        }
    }

    private async Task SkipAllAsync()
    {
        if (_api is null) return;
        try
        {
            await _api.SkipPendingAsync().ConfigureAwait(true);
            StatusLabel = "Skipped — moved to _skipped/.";
        }
        catch (Exception ex)
        {
            StatusLabel = "Error: " + ex.Message;
        }
    }

    /// <summary>Apply a "pending" WS frame; backend always sends the full list.</summary>
    public void OnPendingFrame(IReadOnlyList<PendingItemDto> items) => Replace(items);

    private void Replace(IReadOnlyList<PendingItemDto> items)
    {
        Items.Clear();
        foreach (var item in items) Items.Add(item);
    }
}
