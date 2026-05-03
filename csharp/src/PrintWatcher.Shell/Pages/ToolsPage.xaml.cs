using Microsoft.UI.Xaml.Controls;
using PrintWatcher.Shell.ViewModels;

namespace PrintWatcher.Shell.Pages;

public sealed partial class ToolsPage : Page
{
    public ToolsPage()
    {
        InitializeComponent();
        ViewModel = App.Current.Shell?.Tools ?? new ToolsViewModel();
    }

    public ToolsViewModel ViewModel { get; }
}
