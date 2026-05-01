using System.Text.Json.Serialization;

namespace PrintWatcher.Shell.Models;

public sealed record PrintOptionsDto
{
    [JsonPropertyName("printer")]
    public string? Printer { get; init; }

    [JsonPropertyName("copies")]
    public int Copies { get; init; } = 1;

    [JsonPropertyName("sides")]
    public string? Sides { get; init; }   // null | "simplex" | "duplex" | "duplexshort"

    [JsonPropertyName("color")]
    public string? Color { get; init; }   // null | "color" | "monochrome"
}
