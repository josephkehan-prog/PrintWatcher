using Microsoft.UI.Xaml.Controls;
using PrintWatcher.Shell.ViewModels;

namespace PrintWatcher.Shell.Pages;

public sealed partial class HistoryPage : Page
{
    public HistoryPage()
    {
        InitializeComponent();
        ViewModel = App.Current.Shell?.History ?? new HistoryViewModel();
    }

    public HistoryViewModel ViewModel { get; }
}
