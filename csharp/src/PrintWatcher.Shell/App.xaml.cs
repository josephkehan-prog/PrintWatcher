using System;
using System.Text.Json;
using System.Threading.Tasks;
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
    public NotifyIconService? NotifyIcon { get; private set; }
    public ThemeService Theme { get; } = new();

    /// <summary>
    /// True once <see cref="QuitAsync"/> begins teardown. Read by
    /// <see cref="MainWindow"/>'s closing handler to distinguish "user
    /// clicked X → hide to tray" from "tray Quit → real exit".
    /// </summary>
    public bool ShuttingDown => _shuttingDown;

    private MainWindow? _window;
    private DispatcherQueue? _ui;
    private bool _shuttingDown;

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
            settings: new SettingsViewModel(Api, Theme.Apply, () => backend.LogTail),
            options: new OptionsViewModel((dto, ct) => Api.PutOptionsAsync(dto, ct)));
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
                Shell.Options.ApplyOptions(snapshot.Options);
                Shell.Options.ApplyPrinters(snapshot.Printers);
            }
            await Shell.History.RefreshAsync();
        }
        catch (Exception ex)
        {
            // Surface as a log line for the dashboard rather than crashing.
            backend.Push("ERR initial /api/state failed: " + ex.Message);
        }

        _window = new MainWindow();
        NotifyIcon = new NotifyIconService(() => _window, Api, QuitAsync);
        // Keep the tray menu's Pause/Resume label in sync with the dashboard.
        Shell.Dashboard.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(DashboardViewModel.Paused))
                NotifyIcon?.SetPaused(Shell.Dashboard.Paused);
        };
        NotifyIcon.SetPaused(Shell.Dashboard.Paused);
        _window.Activate();
    }

    private async Task QuitAsync()
    {
        if (_shuttingDown) return;
        _shuttingDown = true;
        try
        {
            if (Api is not null) await Api.PostShutdownAsync();
        }
        catch
        {
            // Backend may have died already; supervisor disposal will reap it.
        }
        if (Backend is not null) await Backend.DisposeAsync();
        NotifyIcon?.Dispose();
        Exit();
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
