using System.Text.Json;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.Services;

namespace PrintWatcher.Shell.ViewModels;

/// <summary>
/// App-level VM. Owns child VMs and exposes connection state + theme name
/// for top-level chrome bindings (status pip, theme picker, etc).
/// </summary>
public sealed class ShellViewModel : ObservableObject
{
    private ConnState _connection = ConnState.Connecting;
    private string _theme = "Ocean";

    public ShellViewModel(
        DashboardViewModel dashboard,
        HistoryViewModel history,
        PendingViewModel pending,
        ToolsViewModel tools,
        SettingsViewModel settings,
        OptionsViewModel options)
    {
        Dashboard = dashboard;
        History = history;
        Pending = pending;
        Tools = tools;
        Settings = settings;
        Options = options;
    }

    public DashboardViewModel Dashboard { get; }
    public HistoryViewModel History { get; }
    public PendingViewModel Pending { get; }
    public ToolsViewModel Tools { get; }
    public SettingsViewModel Settings { get; }
    public OptionsViewModel Options { get; }

    public ConnState Connection
    {
        get => _connection;
        set => SetField(ref _connection, value);
    }

    public string Theme
    {
        get => _theme;
        set => SetField(ref _theme, value);
    }

    /// <summary>
    /// Fan a WS frame out to whichever child VM cares about it. Called from
    /// <c>App.xaml.cs</c> after the dispatcher hop, so VMs can mutate
    /// <c>ObservableCollection</c>s safely.
    /// </summary>
    public void OnFrame(string type, JsonElement raw)
    {
        // Dashboard handles stat / log / paused / hello / options; tool
        // stream lines also surface there as activity log entries (the
        // legacy Tk Tools menu does the same).
        Dashboard.OnFrame(type, raw);

        switch (type)
        {
            case "history":
                if (raw.TryGetProperty("record", out var recordEl))
                {
                    var record = recordEl.Deserialize<PrintRecordDto>(JsonContext.Default.PrintRecordDto);
                    if (record is not null) History.OnHistoryFrame(record);
                }
                break;
            case "pending":
                if (raw.TryGetProperty("items", out var itemsEl))
                {
                    var items = itemsEl.Deserialize<System.Collections.Generic.IReadOnlyList<PendingItemDto>>(
                        JsonContext.Default.Options);
                    if (items is not null) Pending.OnPendingFrame(items);
                }
                break;
            case "options":
                if (raw.TryGetProperty("options", out var optsEl))
                {
                    var opts = optsEl.Deserialize<PrintOptionsDto>(JsonContext.Default.PrintOptionsDto);
                    if (opts is not null) Options.ApplyOptions(opts);
                }
                break;
        }
    }
}
