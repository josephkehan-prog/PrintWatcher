using System.Text.Json;
using System.Text.Json.Serialization;

namespace PrintWatcher.Shell.Models;

/// <summary>
/// Catch-all envelope for WebSocket frames. We keep this loose because new
/// event types may land server-side without the shell having to redeploy.
/// Concrete frames are exposed below for the cases the shell actively uses.
/// </summary>
public sealed record WsFrame
{
    [JsonPropertyName("type")] public string Type { get; init; } = "";

    /// <summary>Raw frame JSON for opportunistic field access.</summary>
    public JsonElement Raw { get; init; }
}

public sealed record HelloFrame
{
    [JsonPropertyName("type")] public string Type { get; init; } = "hello";
    [JsonPropertyName("version")] public string Version { get; init; } = "";
    [JsonPropertyName("paused")] public bool Paused { get; init; }
}

public sealed record StatFrame
{
    [JsonPropertyName("type")] public string Type { get; init; } = "stat";
    [JsonPropertyName("key")] public string Key { get; init; } = "";
    [JsonPropertyName("delta")] public int Delta { get; init; }
    [JsonPropertyName("value")] public int Value { get; init; }
}

public sealed record LogFrame
{
    [JsonPropertyName("type")] public string Type { get; init; } = "log";
    [JsonPropertyName("ts")] public string Timestamp { get; init; } = "";
    [JsonPropertyName("level")] public string Level { get; init; } = "info";
    [JsonPropertyName("line")] public string Line { get; init; } = "";
}

public sealed record HistoryFrame
{
    [JsonPropertyName("type")] public string Type { get; init; } = "history";
    [JsonPropertyName("record")] public PrintRecordDto Record { get; init; } = new();
}

public sealed record PendingFrame
{
    [JsonPropertyName("type")] public string Type { get; init; } = "pending";
    [JsonPropertyName("items")] public System.Collections.Generic.IReadOnlyList<PendingItemDto> Items { get; init; }
        = System.Array.Empty<PendingItemDto>();
}

public sealed record ToolFrame
{
    [JsonPropertyName("type")] public string Type { get; init; } = "tool";
    [JsonPropertyName("run_id")] public string RunId { get; init; } = "";
    [JsonPropertyName("stream")] public string Stream { get; init; } = "";
    [JsonPropertyName("line")] public string? Line { get; init; }
    [JsonPropertyName("level")] public string? Level { get; init; }
    [JsonPropertyName("rc")] public int? ExitCode { get; init; }
    [JsonPropertyName("label")] public string? Label { get; init; }
    [JsonPropertyName("module")] public string? Module { get; init; }
    [JsonPropertyName("cancelled")] public bool? Cancelled { get; init; }
}
