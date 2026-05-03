using System;
using System.Text.Json;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using PrintWatcher.Shell.Services;
using PrintWatcher.Shell.ViewModels;

namespace PrintWatcher.Shell;

public partial class App : Application
{
    public static new App Current => (App)Application.Current!;

    public BackendSupervisor? Backend { get; private set; }
    public ApiClient? Api { get; private set; }
    public EventStream? Events { get; private set; }
    public ShellViewModel? Shell { get; private set; }
    public ThemeService Theme { get; } = new();

    private MainWindow? _window;
    private DispatcherQueue? _ui;

    public App()
    {
        InitializeComponent();
        UnhandledException += OnUnhandledException;
    }

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        _ui = DispatcherQueue.GetForCurrentThread();
        Theme.Apply(ThemeRegistry.Default);

        var backend = new BackendSupervisor();
        Backend = backend;
        var info = await backend.StartAsync(BackendLocator.FindBackend());
        Api = new ApiClient(info.BaseAddress, info.Token);
        Events = new EventStream(info.WebSocketAddress, info.Token);

        Shell = new ShellViewModel(
            dashboard: new DashboardViewModel(Api),
            history: new HistoryViewModel(Api),
            pending: new PendingViewModel(Api),
            tools: new ToolsViewModel(Api),
            settings: new SettingsViewModel(Api, Theme.Apply, () => backend.LogTail));
        Events.FrameReceived += OnFrame;
        Events.StateChanged += OnConnState;
        await Events.StartAsync();

        try
        {
            var snapshot = await Api.GetStateAsync();
            if (snapshot is not null)
            {
                Shell.Theme = snapshot.Preferences.Theme;
                Theme.Apply(snapshot.Preferences.Theme);
                Shell.Dashboard.ApplySnapshot(snapshot);
                Shell.Settings.ApplySnapshot(snapshot.Preferences);
                Shell.Pending.OnPendingFrame(snapshot.Pending);
            }
            await Shell.History.RefreshAsync();
        }
        catch (Exception ex)
        {
            // Surface as a log line for the dashboard rather than crashing.
            backend.Push("ERR initial /api/state failed: " + ex.Message);
        }

        _window = new MainWindow();
        _window.Activate();
    }

    private void OnFrame(string type, JsonElement raw)
    {
        // EventStream raises on the read loop's worker thread; ViewModels
        // mutate ObservableCollections that bindings consume, so we must
        // marshal back to the UI dispatcher. ShellViewModel fans the frame
        // out to whichever child VM cares about it.
        _ui?.TryEnqueue(() => Shell?.OnFrame(type, raw));
    }

    private void OnConnState(ConnState state)
    {
        _ui?.TryEnqueue(() =>
        {
            if (Shell is not null) Shell.Connection = state;
        });
    }

    private static void OnUnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs e)
    {
        // Better to log + ignore than to crash the window on a transient blip.
        // Background worker exceptions are already surfaced through the
        // dashboard activity log via the backend supervisor's stderr capture.
        Console.Error.WriteLine($"[unhandled] {e.Message}");
        e.Handled = true;
    }
}
