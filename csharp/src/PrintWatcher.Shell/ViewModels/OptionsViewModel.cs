using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using PrintWatcher.Shell.Models;

namespace PrintWatcher.Shell.ViewModels;

/// <summary>
/// Bound to <c>OptionsPanel</c> on the dashboard. Owns mutable copies of
/// the four print-options fields and a debounced save callback so that
/// a user mashing the copies up-arrow doesn't fire a PUT per click.
/// </summary>
public sealed class OptionsViewModel : ObservableObject
{
    public static readonly IReadOnlyList<string> SidesOptions =
        new[] { "simplex", "duplex", "duplexshort" };

    public static readonly IReadOnlyList<string> ColorOptions =
        new[] { "color", "monochrome" };

    private readonly Func<PrintOptionsDto, CancellationToken, Task>? _save;
    private readonly int _debounceMs;
    private CancellationTokenSource? _pendingCts;
    private bool _suppressSave;

    private IReadOnlyList<string> _printers = Array.Empty<string>();
    private string? _printer;
    private int _copies = 1;
    private string? _sides;
    private string? _color;

    public OptionsViewModel() : this(null, 0) { /* design-time + tests */ }

    public OptionsViewModel(Func<PrintOptionsDto, CancellationToken, Task>? save, int debounceMs = 400)
    {
        _save = save;
        _debounceMs = debounceMs;
    }

    public IReadOnlyList<string> Printers
    {
        get => _printers;
        private set => SetField(ref _printers, value);
    }

    public string? Printer
    {
        get => _printer;
        set { if (SetField(ref _printer, value)) Schedule(); }
    }

    public int Copies
    {
        get => _copies;
        set
        {
            var clamped = Math.Clamp(value, 1, 99);
            if (SetField(ref _copies, clamped))
            {
                Raise(nameof(CopiesDouble));
                Schedule();
            }
        }
    }

    /// <summary>NumberBox.Value is typed double; XAML binds via this wrapper.</summary>
    public double CopiesDouble
    {
        get => _copies;
        set => Copies = (int)System.Math.Round(value);
    }

    public string? Sides
    {
        get => _sides;
        set { if (SetField(ref _sides, value)) Schedule(); }
    }

    public string? Color
    {
        get => _color;
        set { if (SetField(ref _color, value)) Schedule(); }
    }

    /// <summary>Hydrate from a server snapshot or "options" WS frame without firing a save.</summary>
    public void ApplyOptions(PrintOptionsDto options)
    {
        _suppressSave = true;
        try
        {
            Printer = options.Printer;
            Copies = options.Copies;
            Sides = options.Sides;
            Color = options.Color;
        }
        finally
        {
            _suppressSave = false;
        }
    }

    public void ApplyPrinters(PrintersDto printers)
    {
        Printers = printers.List;
        if (string.IsNullOrEmpty(_printer) && !string.IsNullOrEmpty(printers.Default))
        {
            _suppressSave = true;
            try { Printer = printers.Default; }
            finally { _suppressSave = false; }
        }
    }

    public PrintOptionsDto Snapshot() => new()
    {
        Printer = _printer,
        Copies = _copies,
        Sides = _sides,
        Color = _color,
    };

    private void Schedule()
    {
        if (_save is null || _suppressSave) return;
        _pendingCts?.Cancel();
        _pendingCts?.Dispose();
        var cts = new CancellationTokenSource();
        _pendingCts = cts;
        _ = RunDebouncedAsync(cts.Token);
    }

    private async Task RunDebouncedAsync(CancellationToken ct)
    {
        try
        {
            if (_debounceMs > 0) await Task.Delay(_debounceMs, ct).ConfigureAwait(false);
            ct.ThrowIfCancellationRequested();
            if (_save is not null) await _save(Snapshot(), ct).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            // A newer change superseded this one — drop it.
        }
        catch (Exception)
        {
            // Activity log already surfaces backend errors via WS frames.
        }
    }
}
