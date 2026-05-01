using System.Text.Json.Serialization;

namespace PrintWatcher.Shell.Models;

public sealed record PreferencesDto
{
    [JsonPropertyName("theme")] public string Theme { get; init; } = "Ocean";
    [JsonPropertyName("hold_mode")] public bool HoldMode { get; init; }
    [JsonPropertyName("larger_text")] public bool LargerText { get; init; }
    [JsonPropertyName("reduce_transparency")] public bool ReduceTransparency { get; init; }
}
