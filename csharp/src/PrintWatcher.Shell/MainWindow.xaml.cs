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
        var tag = item.Tag as string;
        if (tag == "dashboard")
            ContentFrame.Navigate(typeof(DashboardPage));
        // History / Tools / Settings ship in follow-up PRs.
    }
}
