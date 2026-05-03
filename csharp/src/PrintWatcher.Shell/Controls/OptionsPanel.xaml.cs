using Microsoft.UI.Xaml.Controls;
using PrintWatcher.Shell.ViewModels;

namespace PrintWatcher.Shell.Controls;

public sealed partial class OptionsPanel : UserControl
{
    public OptionsPanel()
    {
        InitializeComponent();
        ViewModel = App.Current.Shell?.Options ?? new OptionsViewModel();
    }

    public OptionsViewModel ViewModel { get; }
}
