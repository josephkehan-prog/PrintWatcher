using System.Text.Json.Serialization;

namespace PrintWatcher.Shell.Models;

public sealed record PendingItemDto
{
    [JsonPropertyName("path")] public string Path { get; init; } = "";
    [JsonPropertyName("name")] public string Name { get; init; } = "";
}
