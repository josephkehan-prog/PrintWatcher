using System.Text.Json.Serialization;

namespace PrintWatcher.Shell.Models;

public sealed record PrintRecordDto
{
    [JsonPropertyName("timestamp")]
    public string Timestamp { get; init; } = "";

    [JsonPropertyName("filename")]
    public string Filename { get; init; } = "";

    [JsonPropertyName("status")]
    public string Status { get; init; } = "";

    [JsonPropertyName("detail")]
    public string Detail { get; init; } = "";

    [JsonPropertyName("printer")]
    public string Printer { get; init; } = "";

    [JsonPropertyName("copies")]
    public int Copies { get; init; } = 1;

    [JsonPropertyName("sides")]
    public string Sides { get; init; } = "";

    [JsonPropertyName("color")]
    public string Color { get; init; } = "";

    [JsonPropertyName("submitter")]
    public string Submitter { get; init; } = "";
}
