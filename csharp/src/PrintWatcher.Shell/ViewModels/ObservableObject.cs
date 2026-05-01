using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace PrintWatcher.Shell.ViewModels;

/// <summary>
/// Minimal INotifyPropertyChanged base. We avoid the MVVM Toolkit dependency
/// because this app's surface is small enough to not justify the source
/// generator, and the explicit setters make the dependency graph obvious.
/// </summary>
public abstract class ObservableObject : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;

    protected bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (System.Collections.Generic.EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        return true;
    }

    protected void Raise([CallerMemberName] string? propertyName = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
}
