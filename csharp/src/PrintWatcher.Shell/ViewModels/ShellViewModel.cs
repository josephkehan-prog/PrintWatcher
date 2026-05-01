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

    public ShellViewModel(DashboardViewModel dashboard)
    {
        Dashboard = dashboard;
    }

    public DashboardViewModel Dashboard { get; }

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
}
