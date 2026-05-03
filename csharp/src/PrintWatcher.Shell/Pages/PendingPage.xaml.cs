using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using PrintWatcher.Shell.ViewModels;

namespace PrintWatcher.Shell.Pages;

public sealed partial class PendingPage : Page
{
    public PendingPage()
    {
        InitializeComponent();
        ViewModel = App.Current.Shell?.Pending ?? new PendingViewModel();
        ViewModel.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(PendingViewModel.IsEmpty))
                Bindings.Update();
        };
    }

    public PendingViewModel ViewModel { get; }

    public Visibility EmptyToVisible(bool isEmpty) => isEmpty ? Visibility.Visible : Visibility.Collapsed;

    public Visibility EmptyToCollapsed(bool isEmpty) => isEmpty ? Visibility.Collapsed : Visibility.Visible;
}
