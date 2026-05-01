using System;

namespace PrintWatcher.Shell.ViewModels;

/// <summary>One entry in the dashboard's stat-tile grid.</summary>
public sealed class StatTileItem : ObservableObject
{
    private readonly Func<int> _read;

    public StatTileItem(string label, Func<int> read)
    {
        Label = label;
        _read = read;
    }

    public string Label { get; }

    public int Value => _read();

    /// <summary>Notify the binding that <see cref="Value"/> may have changed.</summary>
    public void Refresh() => Raise(nameof(Value));
}
