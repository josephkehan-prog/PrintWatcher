using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.Services;

namespace PrintWatcher.Shell.ViewModels;

/// <summary>
/// One row in the Tools page — a script name, the args to pass, a friendly
/// label, and the command that fires <c>POST /api/tools/run</c>. Output
/// streams back as "tool" WS frames which the dashboard activity log
/// surfaces.
/// </summary>
public sealed class ToolDescriptor
{
    public required string Module { get; init; }
    public required string Label { get; init; }
    public required string Description { get; init; }
    public IReadOnlyList<string> Args { get; init; } = Array.Empty<string>();
    public AsyncRelayCommand? RunCommand { get; init; }
}

public sealed class ToolsViewModel : ObservableObject
{
    private readonly ApiClient? _api;
    private string _statusLabel = "";

    public ToolsViewModel() { /* design-time + tests */ }

    public ToolsViewModel(ApiClient api)
    {
        _api = api;
        Tools = BuildCatalog();
    }

    public IReadOnlyList<ToolDescriptor> Tools { get; } = Array.Empty<ToolDescriptor>();

    public string StatusLabel
    {
        get => _statusLabel;
        private set => SetField(ref _statusLabel, value);
    }

    private IReadOnlyList<ToolDescriptor> BuildCatalog()
    {
        // Mirrors the legacy Tk Tools menu (print_watcher_ui.py:1539+).
        // Output and log lines stream back over the WS as "tool" frames.
        var defs = new (string Module, string Label, string Description, string[] Args)[]
        {
            ("scripts.verify_environment", "Verify environment",
                "Diagnostic: Python, SumatraPDF, OneDrive paths, default printer.", Array.Empty<string>()),
            ("scripts.printer_test", "Calibration page",
                "One-page test sheet — rulers, color bars, font samples.", new[] { "--to-inbox" }),
            ("scripts.weekly_report", "Weekly report",
                "PDF summary of this week's prints. Drops in inbox.", new[] { "--to-inbox" }),
            ("scripts.dedupe_inbox", "Dedupe inbox (dry-run)",
                "Hash-based duplicate scan. Reports only — no changes.", Array.Empty<string>()),
            ("scripts.cleanup_printed", "Clean _printed/ (dry-run)",
                "Sweep files older than 30 days. Reports only — no changes.", Array.Empty<string>()),
            ("scripts.history_search", "Recent prints",
                "Last 7 days of history as a table.", new[] { "--last-days", "7" }),
        };

        var result = new List<ToolDescriptor>(defs.Length);
        foreach (var def in defs)
        {
            ToolDescriptor descriptor = null!;
            descriptor = new ToolDescriptor
            {
                Module = def.Module,
                Label = def.Label,
                Description = def.Description,
                Args = def.Args,
                RunCommand = new AsyncRelayCommand(() => RunAsync(descriptor)),
            };
            result.Add(descriptor);
        }
        return result;
    }

    private static string Shorten(string id) =>
        string.IsNullOrEmpty(id) ? "?" : id.Length <= 8 ? id : id[..8];

    private async Task RunAsync(ToolDescriptor descriptor)
    {
        if (_api is null) return;
        try
        {
            var started = await _api.RunToolAsync(new ToolRunRequestDto
            {
                Module = descriptor.Module,
                Args = descriptor.Args,
                Label = descriptor.Label,
            }).ConfigureAwait(true);
            StatusLabel = started is null
                ? "Run requested."
                : $"Running '{started.Label}' ({Shorten(started.RunId)}) — see Activity log.";
        }
        catch (Exception ex)
        {
            StatusLabel = "Error: " + ex.Message;
        }
    }
}
