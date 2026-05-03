using Microsoft.UI.Xaml.Controls;
using PrintWatcher.Shell.ViewModels;

namespace PrintWatcher.Shell.Pages;

public sealed partial class SettingsPage : Page
{
    public SettingsPage()
    {
        InitializeComponent();
        ViewModel = App.Current.Shell?.Settings ?? new SettingsViewModel();
    }

    public SettingsViewModel ViewModel { get; }
}
