using System.Text.Json.Serialization;

namespace PrintWatcher.Shell.Models;

/// <summary>
/// System.Text.Json source generation entry. Adding a new DTO to the wire
/// surface? Append it here so the AOT-friendly serializer picks it up.
/// </summary>
[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    WriteIndented = false)]
[JsonSerializable(typeof(StateDto))]
[JsonSerializable(typeof(PrintOptionsDto))]
[JsonSerializable(typeof(PrintRecordDto))]
[JsonSerializable(typeof(StatsDto))]
[JsonSerializable(typeof(PendingItemDto))]
[JsonSerializable(typeof(PrintersDto))]
[JsonSerializable(typeof(PreferencesDto))]
[JsonSerializable(typeof(PauseDto))]
[JsonSerializable(typeof(ToolRunRequestDto))]
[JsonSerializable(typeof(ToolRunStartedDto))]
[JsonSerializable(typeof(HelloFrame))]
[JsonSerializable(typeof(StatFrame))]
[JsonSerializable(typeof(LogFrame))]
[JsonSerializable(typeof(HistoryFrame))]
[JsonSerializable(typeof(PendingFrame))]
[JsonSerializable(typeof(ToolFrame))]
[JsonSerializable(typeof(System.Collections.Generic.IReadOnlyList<PrintRecordDto>))]
[JsonSerializable(typeof(System.Collections.Generic.IReadOnlyList<PendingItemDto>))]
public sealed partial class JsonContext : JsonSerializerContext
{
}
