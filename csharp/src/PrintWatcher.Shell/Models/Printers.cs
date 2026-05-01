using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace PrintWatcher.Shell.Models;

public sealed record PrintersDto
{
    [JsonPropertyName("default")] public string? Default { get; init; }
    [JsonPropertyName("list")] public IReadOnlyList<string> List { get; init; } = System.Array.Empty<string>();
}
