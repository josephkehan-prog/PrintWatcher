using System;
using Microsoft.Windows.AppNotifications;
using Microsoft.Windows.AppNotifications.Builder;

namespace PrintWatcher.Shell.Services;

/// <summary>
/// Thin wrapper around <see cref="AppNotificationManager"/> for Windows
/// toast notifications. The shell uses this to surface successful prints
/// (auto-dismiss) and errors (persistent) without forcing the user back
/// to the dashboard.
///
/// Notifications are best-effort: any failure (manager unavailable,
/// notification permissions denied, unpackaged-mode quirks) is swallowed
/// so a toast subsystem outage never blocks the watcher's hot path.
/// </summary>
public sealed class ToastService
{
    private readonly AppNotificationManager? _manager;

    public ToastService()
    {
        try
        {
            _manager = AppNotificationManager.Default;
            _manager.Register();
        }
        catch (Exception)
        {
            // Toast manager unavailable — running unpackaged without the
            // notification capability, or test host. Swallow and become a
            // no-op service.
            _manager = null;
        }
    }

    /// <summary>Notify on a successful print job.</summary>
    public void NotifyPrinted(string filename, string printer)
    {
        if (_manager is null) return;
        try
        {
            var n = new AppNotificationBuilder()
                .AddText("Printed")
                .AddText(filename)
                .AddText(string.IsNullOrWhiteSpace(printer) ? "default printer" : $"to {printer}")
                .BuildNotification();
            // Auto-dismiss; success toasts shouldn't pile up in Action Center.
            n.ExpiresOnReboot = true;
            _manager.Show(n);
        }
        catch (Exception)
        {
            // Best-effort — see class doc.
        }
    }

    /// <summary>Notify on a print error. Persistent in Action Center.</summary>
    public void NotifyError(string filename, string detail)
    {
        if (_manager is null) return;
        try
        {
            var n = new AppNotificationBuilder()
                .AddText("Print failed")
                .AddText(filename)
                .AddText(string.IsNullOrWhiteSpace(detail) ? "see History tab" : detail)
                .BuildNotification();
            _manager.Show(n);
        }
        catch (Exception)
        {
            // Best-effort — see class doc.
        }
    }
}
