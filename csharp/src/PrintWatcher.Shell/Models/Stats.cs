using System.Text.Json.Serialization;

namespace PrintWatcher.Shell.Models;

public sealed record StatsDto
{
    [JsonPropertyName("printed")] public int Printed { get; init; }
    [JsonPropertyName("today")] public int Today { get; init; }
    [JsonPropertyName("pending")] public int Pending { get; init; }
    [JsonPropertyName("errors")] public int Errors { get; init; }
}
