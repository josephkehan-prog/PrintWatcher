using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using PrintWatcher.Shell.Pages;
using PrintWatcher.Shell.Services;

namespace PrintWatcher.Shell;

public sealed partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        Title = "PrintWatcher";
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);

        // Backdrop picks itself based on the active palette: translucent
        // themes (Glass) get DesktopAcrylicBackdrop so window content blurs
        // through panel surfaces; everything else stays on Mica.
        var theme = App.Current.Theme;
        ApplyBackdrop(ThemeRegistry.Resolve(theme.Current));
        theme.ThemeChanged += OnThemeChanged;

        AppWindow.Closing += OnAppWindowClosing;
        ContentFrame.Navigate(typeof(DashboardPage));
    }

    private void OnThemeChanged(ThemePalette palette) => ApplyBackdrop(palette);

    private void ApplyBackdrop(ThemePalette palette)
    {
        SystemBackdrop = palette.Translucent
            ? new DesktopAcrylicBackdrop()
            : new MicaBackdrop { Kind = Microsoft.UI.Composition.SystemBackdrops.MicaKind.BaseAlt };
    }

    private static void OnAppWindowClosing(
        Microsoft.UI.Windowing.AppWindow sender,
        Microsoft.UI.Windowing.AppWindowClosingEventArgs args)
    {
        try
        {
            // Tray Quit path — let the close go through.
            if (App.Current.ShuttingDown) return;
            args.Cancel = true;
            App.Current.NotifyIcon?.HideWindow();
        }
        catch (InvalidOperationException)
        {
            // App.Current isn't ready during very-late shutdown — fall through.
        }
    }

    private void OnNavigationSelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (args.SelectedItem is not NavigationViewItem item) return;
        var pageType = (item.Tag as string) switch
        {
            "dashboard" => typeof(DashboardPage),
            "history"   => typeof(HistoryPage),
            "pending"   => typeof(PendingPage),
            "tools"     => typeof(ToolsPage),
            "settings"  => typeof(SettingsPage),
            _           => null,
        };
        if (pageType is null) return;
        if (ContentFrame.CurrentSourcePageType == pageType) return;
        ContentFrame.Navigate(pageType);
    }
}
