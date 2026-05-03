using System;
using System.IO;
using System.Threading.Tasks;
using H.NotifyIcon;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using PrintWatcher.Shell.Models;

namespace PrintWatcher.Shell.Services;

/// <summary>
/// Owns the system tray icon for the lifetime of the app.
///
/// The tray sticks around when the user closes the window — closing
/// becomes "hide to tray", and only the tray's Quit menu actually exits.
/// This matches the legacy Tk pystray behaviour and is what users expect
/// from a printer-watcher background app.
/// </summary>
public sealed class NotifyIconService : IDisposable
{
    private readonly TaskbarIcon _taskbarIcon;
    private readonly Func<Window?> _resolveWindow;
    private readonly ApiClient _api;
    private readonly Func<Task> _quit;
    private readonly MenuFlyoutItem _pauseItem;
    private bool _paused;

    public NotifyIconService(Func<Window?> resolveWindow, ApiClient api, Func<Task> quit)
    {
        _resolveWindow = resolveWindow;
        _api = api;
        _quit = quit;

        _pauseItem = new MenuFlyoutItem { Text = "Pause" };
        _pauseItem.Click += async (_, _) => await TogglePauseAsync().ConfigureAwait(true);

        var openItem = new MenuFlyoutItem { Text = "Open" };
        openItem.Click += (_, _) => ShowWindow();

        var quitItem = new MenuFlyoutItem { Text = "Quit" };
        quitItem.Click += async (_, _) => await _quit().ConfigureAwait(true);

        var menu = new MenuFlyout();
        menu.Items.Add(openItem);
        menu.Items.Add(_pauseItem);
        menu.Items.Add(new MenuFlyoutSeparator());
        menu.Items.Add(quitItem);

        // H.NotifyIcon's IconSource is typed Microsoft.UI.Xaml.Media.ImageSource —
        // BitmapImage is the only ImageSource that works for unpackaged WinUI
        // 3. We point at the PNG (rather than the .ico) because BitmapImage
        // doesn't render multi-resolution .ico files reliably in WinUI 3
        // unpackaged. The window chrome and Start-menu entry still use the
        // .ico via Package.appxmanifest / ApplicationIcon.
        var iconPath = Path.Combine(AppContext.BaseDirectory, "Assets", "Square44x44Logo.png");
        _taskbarIcon = new TaskbarIcon
        {
            ToolTipText = "PrintWatcher",
            IconSource = new BitmapImage(new Uri(iconPath)),
            ContextFlyout = menu,
        };
        _taskbarIcon.LeftClickCommand = new RelayLeftClickCommand(ShowWindow);
        _taskbarIcon.ForceCreate();
    }

    /// <summary>Echo the current paused state from the dashboard so the menu reads correctly.</summary>
    public void SetPaused(bool paused)
    {
        _paused = paused;
        _pauseItem.Text = paused ? "Resume" : "Pause";
    }

    public void ShowWindow()
    {
        var window = _resolveWindow();
        if (window is null) return;
        window.AppWindow.Show();
        window.Activate();
    }

    public void HideWindow()
    {
        var window = _resolveWindow();
        window?.AppWindow.Hide();
    }

    private async Task TogglePauseAsync()
    {
        try
        {
            var echo = await _api.PostPauseAsync(!_paused).ConfigureAwait(true);
            if (echo is not null) SetPaused(echo.Paused);
        }
        catch
        {
            // The dashboard's status pip already surfaces connection issues;
            // silently ignoring here keeps the tray menu from throwing.
        }
    }

    public void Dispose() => _taskbarIcon.Dispose();

    /// <summary>
    /// Single-shot ICommand that fires the supplied callback. H.NotifyIcon's
    /// LeftClickCommand wants an ICommand, but we only need the action.
    /// </summary>
    private sealed class RelayLeftClickCommand : System.Windows.Input.ICommand
    {
        private readonly Action _handler;
        public RelayLeftClickCommand(Action handler) => _handler = handler;
        public event EventHandler? CanExecuteChanged { add { } remove { } }
        public bool CanExecute(object? parameter) => true;
        public void Execute(object? parameter) => _handler();
    }
}
