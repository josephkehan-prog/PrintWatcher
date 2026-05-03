using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;

namespace PrintWatcher.Shell.Controls;

/// <summary>
/// Tiny status indicator in the dashboard header. Breathes (~0.5 Hz opacity
/// pulse) while the watcher is active; goes solid + opaque the instant it
/// pauses. The single distinctive moment of motion in the shell — calmer
/// than scattered hover micro-interactions on every control.
/// </summary>
public sealed partial class StatusPip : UserControl
{
    public static readonly DependencyProperty IsActiveProperty =
        DependencyProperty.Register(
            nameof(IsActive),
            typeof(bool),
            typeof(StatusPip),
            new PropertyMetadata(true, OnIsActiveChanged));

    public StatusPip()
    {
        InitializeComponent();
        Loaded += (_, _) => UpdateAnimation();
    }

    public bool IsActive
    {
        get => (bool)GetValue(IsActiveProperty);
        set => SetValue(IsActiveProperty, value);
    }

    private static void OnIsActiveChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is StatusPip pip) pip.UpdateAnimation();
    }

    private void UpdateAnimation()
    {
        var visual = ElementCompositionPreview.GetElementVisual(Pip);
        var compositor = visual.Compositor;
        // Always cancel any prior animation before starting a new one.
        visual.StopAnimation("Opacity");

        if (!IsActive)
        {
            visual.Opacity = 1.0f;
            return;
        }

        var animation = compositor.CreateScalarKeyFrameAnimation();
        animation.InsertKeyFrame(0.0f, 1.0f);
        animation.InsertKeyFrame(0.5f, 0.35f);
        animation.InsertKeyFrame(1.0f, 1.0f);
        animation.Duration = System.TimeSpan.FromMilliseconds(2000);
        animation.IterationBehavior = AnimationIterationBehavior.Forever;
        visual.StartAnimation("Opacity", animation);
    }
}
