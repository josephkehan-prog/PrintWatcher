using System;
using System.Numerics;
using System.Runtime.CompilerServices;
using Microsoft.UI.Xaml;

namespace PrintWatcher.Shell.Services;

/// <summary>
/// Attached property that lifts a glass surface off the acrylic backdrop and
/// flattens it again on solid (Mica) palettes. Set
/// <c>svc:GlassDepth.Elevated="True"</c> on any surface that also assigns a
/// <c>Shadow</c>; the <c>Translation</c> Z is driven from the active theme here,
/// so opaque themes stay flat (Z = 0 → no cast) and a live theme switch updates
/// every visible surface.
/// </summary>
/// <remarks>
/// Subscriptions are scoped to the element's <see cref="FrameworkElement.Loaded"/>
/// / <see cref="FrameworkElement.Unloaded"/> lifetime so navigating between pages
/// — or recycling tiles in an <c>ItemsRepeater</c> — doesn't leak
/// <see cref="ThemeService.ThemeChanged"/> handlers. This relies on Loaded/Unloaded
/// being raised on recycle, which holds for DataTemplate-based ItemsRepeater but
/// not necessarily for a custom <c>ElementFactory</c>.
/// </remarks>
public static class GlassDepth
{
    private sealed class Subscription
    {
        public required ThemeService Theme { get; init; }
        public required Action<ThemePalette> Handler { get; init; }
    }

    // Keyed by element so a recycled/navigated-away surface drops its handler.
    // The ThemeService is captured here (not re-fetched via App.Current) so
    // Unhook can always unsubscribe, even during late teardown when App.Current
    // may no longer be reachable.
    private static readonly ConditionalWeakTable<FrameworkElement, Subscription> Subscriptions = new();

    public static readonly DependencyProperty ElevatedProperty =
        DependencyProperty.RegisterAttached(
            "Elevated", typeof(bool), typeof(GlassDepth),
            new PropertyMetadata(false, OnElevatedChanged));

    public static bool GetElevated(DependencyObject obj) => (bool)obj.GetValue(ElevatedProperty);

    public static void SetElevated(DependencyObject obj, bool value) => obj.SetValue(ElevatedProperty, value);

    private static void OnElevatedChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is not FrameworkElement element) return;

        element.Loaded -= OnLoaded;
        element.Unloaded -= OnUnloaded;

        if ((bool)e.NewValue)
        {
            element.Loaded += OnLoaded;
            element.Unloaded += OnUnloaded;
            if (element.IsLoaded) Hook(element);
        }
        else
        {
            Unhook(element);
        }
    }

    private static void OnLoaded(object sender, RoutedEventArgs e) => Hook((FrameworkElement)sender);

    private static void OnUnloaded(object sender, RoutedEventArgs e) => Unhook((FrameworkElement)sender);

    private static void Hook(FrameworkElement element)
    {
        var theme = App.Current?.Theme;
        if (theme is null) return;

        ApplyZ(element, ThemeRegistry.Resolve(theme.Current), theme.ReduceTransparency);

        if (Subscriptions.TryGetValue(element, out _)) return; // already subscribed
        Action<ThemePalette> handler = palette => ApplyZ(element, palette, theme.ReduceTransparency);
        Subscriptions.Add(element, new Subscription { Theme = theme, Handler = handler });
        theme.ThemeChanged += handler;
    }

    private static void Unhook(FrameworkElement element)
    {
        if (!Subscriptions.TryGetValue(element, out var sub)) return;
        sub.Theme.ThemeChanged -= sub.Handler;
        Subscriptions.Remove(element);
    }

    private static void ApplyZ(UIElement element, ThemePalette palette, bool reduceTransparency) =>
        element.Translation = new Vector3(0f, 0f, (float)GlassMaterial.ElevationZ(palette, reduceTransparency));
}
