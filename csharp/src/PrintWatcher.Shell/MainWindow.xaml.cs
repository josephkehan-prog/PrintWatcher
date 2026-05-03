using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using PrintWatcher.Shell.Pages;

namespace PrintWatcher.Shell;

public sealed partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        Title = "PrintWatcher";
        SystemBackdrop = new MicaBackdrop { Kind = Microsoft.UI.Composition.SystemBackdrops.MicaKind.BaseAlt };
        ExtendsContentIntoTitleBar = true;
        ContentFrame.Navigate(typeof(DashboardPage));
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
