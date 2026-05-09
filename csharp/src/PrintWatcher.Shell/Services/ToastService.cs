using System.Diagnostics;

namespace PrintWatcher.Shell.Services;

/// <summary>
/// Toast notification stub.
///
/// The full implementation calls <c>Microsoft.Windows.AppNotifications.AppNotificationManager</c>
/// which requires additional unpackaged-mode setup (a COM activator
/// registration in the manifest). Until that wiring is in place we keep
/// the type as a no-op so the WinUI build stays clean and the dashboard
/// + history surfaces still call something sensible. Reintroducing real
/// toasts is a small follow-up: swap the body of <see cref="NotifyPrinted"/>
/// and <see cref="NotifyError"/> with <c>AppNotificationBuilder</c>
/// once the manifest is updated.
/// </summary>
public sealed class ToastService
{
    public void NotifyPrinted(string filename, string printer)
    {
        Debug.WriteLine($"[toast] printed: {filename} → {printer}");
    }

    public void NotifyError(string filename, string detail)
    {
        Debug.WriteLine($"[toast] error: {filename} ({detail})");
    }
}
