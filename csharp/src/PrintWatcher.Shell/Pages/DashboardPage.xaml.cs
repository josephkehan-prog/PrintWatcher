using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using PrintWatcher.Shell.ViewModels;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;

namespace PrintWatcher.Shell.Pages;

public sealed partial class DashboardPage : Page
{
    public DashboardPage()
    {
        InitializeComponent();
        ViewModel = App.Current.Shell?.Dashboard ?? new DashboardViewModel();
        StatTiles = BuildTiles(ViewModel);
        ViewModel.PropertyChanged += OnViewModelChanged;
        AllowDrop = true;
        DragOver += OnDragOver;
        Drop += OnDrop;
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
        if (e.PropertyName == nameof(DashboardViewModel.Paused))
            Bindings.Update();
    }

    /// <summary>x:Bind function-binding helper — StatusPip.IsActive = !Paused.</summary>
    public bool Negate(bool value) => !value;

    private static void OnDragOver(object sender, DragEventArgs e)
    {
        if (e.DataView.Contains(StandardDataFormats.StorageItems))
        {
            e.AcceptedOperation = DataPackageOperation.Copy;
            e.DragUIOverride.Caption = "Drop to print";
            e.DragUIOverride.IsCaptionVisible = true;
            e.DragUIOverride.IsContentVisible = true;
        }
    }

    private async void OnDrop(object sender, DragEventArgs e)
    {
        if (!e.DataView.Contains(StandardDataFormats.StorageItems)) return;
        var deferral = e.GetDeferral();
        try
        {
            var items = await e.DataView.GetStorageItemsAsync();
            var api = App.Current.Api;
            if (api is null) return;
            foreach (var file in items.OfType<StorageFile>())
            {
                try
                {
                    await api.UploadInboxAsync(file.Path);
                }
                catch (Exception ex)
                {
                    App.Current.Backend?.Push("ERR upload " + file.Name + ": " + ex.Message);
                }
            }
        }
        finally
        {
            deferral.Complete();
        }
    }
}
