using System;
using System.Text.Json.Serialization;

namespace PrintWatcher.Shell.Models;

public sealed record UpdateCheckDto
{
    [JsonPropertyName("current")] public string Current { get; init; } = "";
    [JsonPropertyName("latest")] public string? Latest { get; init; }
    [JsonPropertyName("html_url")] public string? HtmlUrl { get; init; }
    [JsonPropertyName("has_update")] public bool HasUpdate { get; init; }
    [JsonPropertyName("checked_at")] public DateTimeOffset? CheckedAt { get; init; }
}
