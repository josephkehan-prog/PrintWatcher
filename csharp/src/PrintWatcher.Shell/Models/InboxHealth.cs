using System.Text.Json.Serialization;

namespace PrintWatcher.Shell.Models;

public sealed record InboxHealthDto
{
    [JsonPropertyName("watch_dir")] public string WatchDir { get; init; } = "";
    [JsonPropertyName("inbox_count")] public int InboxCount { get; init; }
    [JsonPropertyName("inbox_bytes")] public long InboxBytes { get; init; }
    [JsonPropertyName("printed_count")] public int PrintedCount { get; init; }
    [JsonPropertyName("printed_bytes")] public long PrintedBytes { get; init; }
    [JsonPropertyName("skipped_count")] public int SkippedCount { get; init; }
    [JsonPropertyName("skipped_bytes")] public long SkippedBytes { get; init; }
    [JsonPropertyName("scheduled_count")] public int ScheduledCount { get; init; }
    [JsonPropertyName("scheduled_bytes")] public long ScheduledBytes { get; init; }
    [JsonPropertyName("total_bytes")] public long TotalBytes { get; init; }
}
