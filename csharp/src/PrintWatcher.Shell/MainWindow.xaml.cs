using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;

namespace PrintWatcher.Shell;

public sealed partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        Title = "PrintWatcher";
        SystemBackdrop = new MicaBackdrop { Kind = Microsoft.UI.Composition.SystemBackdrops.MicaKind.BaseAlt };
        ExtendsContentIntoTitleBar = true;
    }
}
