using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace PrintWatcher.Shell.Models;

public sealed record StateDto
{
    [JsonPropertyName("version")] public string Version { get; init; } = "";
    [JsonPropertyName("stats")] public StatsDto Stats { get; init; } = new();
    [JsonPropertyName("paused")] public bool Paused { get; init; }
    [JsonPropertyName("options")] public PrintOptionsDto Options { get; init; } = new();
    [JsonPropertyName("pending")] public IReadOnlyList<PendingItemDto> Pending { get; init; } = System.Array.Empty<PendingItemDto>();
    [JsonPropertyName("preferences")] public PreferencesDto Preferences { get; init; } = new();
    [JsonPropertyName("printers")] public PrintersDto Printers { get; init; } = new();
}

public sealed record PauseDto
{
    [JsonPropertyName("paused")] public bool Paused { get; init; }
}

public sealed record ToolRunRequestDto
{
    [JsonPropertyName("module")] public string Module { get; init; } = "";
    [JsonPropertyName("args")] public IReadOnlyList<string> Args { get; init; } = System.Array.Empty<string>();
    [JsonPropertyName("label")] public string? Label { get; init; }
}

public sealed record ToolRunStartedDto
{
    [JsonPropertyName("run_id")] public string RunId { get; init; } = "";
    [JsonPropertyName("label")] public string Label { get; init; } = "";
}
