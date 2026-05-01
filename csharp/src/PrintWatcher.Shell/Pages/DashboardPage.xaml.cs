using System.Collections.Generic;
using System.ComponentModel;
using Microsoft.UI.Xaml.Controls;
using PrintWatcher.Shell.ViewModels;

namespace PrintWatcher.Shell.Pages;

public sealed partial class DashboardPage : Page
{
    public DashboardPage()
    {
        InitializeComponent();
        ViewModel = App.Current.Shell?.Dashboard ?? new DashboardViewModel();
        StatTiles = BuildTiles(ViewModel);
        ViewModel.PropertyChanged += OnViewModelChanged;
    }

    public DashboardViewModel ViewModel { get; }

    public IReadOnlyList<StatTileItem> StatTiles { get; }

    private static StatTileItem[] BuildTiles(DashboardViewModel vm) => new[]
    {
        new StatTileItem("PRINTED", () => vm.Printed),
        new StatTileItem("TODAY", () => vm.Today),
        new StatTileItem("PENDING", () => vm.Pending),
        new StatTileItem("ERRORS", () => vm.Errors),
    };

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        foreach (var tile in StatTiles)
            tile.Refresh();
    }
}
