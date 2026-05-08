using Microsoft.UI.Xaml.Controls;
using PrintWatcher.Shell.Models;
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

    private async void OnReprintClicked(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
    {
        // The MenuFlyoutItem's DataContext is the row's PrintRecordDto.
        if (sender is MenuFlyoutItem item && item.DataContext is PrintRecordDto record)
        {
            await ViewModel.ReprintAsync(record);
        }
    }
}
