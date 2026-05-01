using System;
using Microsoft.UI.Xaml;
using PrintWatcher.Shell.Services;

namespace PrintWatcher.Shell;

public partial class App : Application
{
    public static new App Current => (App)Application.Current!;
    public BackendSupervisor? Backend { get; private set; }
    public ApiClient? Api { get; private set; }
    public EventStream? Events { get; private set; }

    private MainWindow? _window;

    public App()
    {
        InitializeComponent();
        UnhandledException += OnUnhandledException;
    }

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        Backend = new BackendSupervisor();
        var info = await Backend.StartAsync(BackendLocator.FindBackend());
        Api = new ApiClient(info.BaseAddress, info.Token);
        Events = new EventStream(info.WebSocketAddress, info.Token);

        _window = new MainWindow();
        _window.Activate();
    }

    private static void OnUnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs e)
    {
        // Log and continue — closing the window on every transient blip is worse
        // than a logged warning the user can ignore.
        Console.Error.WriteLine($"[unhandled] {e.Message}");
        e.Handled = true;
    }
}
