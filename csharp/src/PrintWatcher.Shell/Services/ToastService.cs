using System.Diagnostics;

namespace PrintWatcher.Shell.Services;

/// <summary>Stub until the unpackaged-mode COM activator manifest entry lands.</summary>
public sealed class ToastService
{
    public void NotifyPrinted(string filename, string printer)
    {
        // TODO(toast): swap for AppNotificationBuilder once the manifest's
        // COM activator class is registered for unpackaged WinUI 3.
        Debug.WriteLine($"[toast] printed: {filename} -> {printer}");
    }

    public void NotifyError(string filename, string detail)
    {
        // TODO(toast): swap for AppNotificationBuilder once the manifest's
        // COM activator class is registered for unpackaged WinUI 3.
        Debug.WriteLine($"[toast] error: {filename} ({detail})");
    }
}
