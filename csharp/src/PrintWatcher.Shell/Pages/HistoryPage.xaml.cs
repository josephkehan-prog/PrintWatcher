using System;
using System.Diagnostics;
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

    private void OnOpenPrinterQueueClicked(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
    {
        if (sender is not MenuFlyoutItem item || item.DataContext is not PrintRecordDto record)
            return;
        if (string.IsNullOrWhiteSpace(record.Printer))
            return;
        try
        {
            // rundll32 printui.dll,PrintUIEntry /o /n "<printer>" opens the
            // Windows printer queue UI for the named printer.
            Process.Start(new ProcessStartInfo
            {
                FileName = "rundll32.exe",
                Arguments = $"printui.dll,PrintUIEntry /o /n \"{record.Printer}\"",
                UseShellExecute = true,
            });
        }
        catch (Exception ex)
        {
            // Surfacing failure via StatusLabel keeps the failure visible
            // without a modal dialog.
            ViewModel.SetTransientStatus($"Open printer queue failed: {ex.Message}");
        }
    }
}
