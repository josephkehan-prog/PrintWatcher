"""DTO parity test — Python Pydantic models ↔ C# shell records.

Parses the C# `Models/*.cs` files for `[JsonPropertyName("...")]` keys and
asserts that every name the shell expects is present on the matching Python
DTO. Catches drift like renaming a field on one side without the other.

Allows the Python side to have extra fields (forward-compat); fails when
the shell expects a key the server does not produce.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from printwatcher.server import dto

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "csharp" / "src" / "PrintWatcher.Shell" / "Models"

CSHARP_TO_PY = {
    "StateDto": dto.StateDto,
    "StatsDto": dto.StatsDto,
    "PrintRecordDto": dto.PrintRecordDto,
    "PrintOptionsDto": dto.PrintOptionsDto,
    "PendingItemDto": dto.PendingItemDto,
    "PrintersDto": dto.PrintersDto,
    "PreferencesDto": dto.PreferencesDto,
    "PauseDto": dto.PauseDto,
    "ToolRunStartedDto": dto.ToolRunStartedDto,
}

_RECORD_RE = re.compile(r"public sealed record (\w+)\s*\{([^}]*)\}", re.DOTALL)
_PROP_RE = re.compile(r'\[JsonPropertyName\("([^"]+)"\)\]')


def _parse_csharp_records() -> dict[str, set[str]]:
    """Return ``{record_name: {json_key, ...}}`` for every record in Models/."""
    records: dict[str, set[str]] = {}
    if not MODELS_DIR.exists():
        pytest.skip(f"shell models directory not found: {MODELS_DIR}")
    for cs_file in MODELS_DIR.glob("*.cs"):
        text = cs_file.read_text(encoding="utf-8")
        for match in _RECORD_RE.finditer(text):
            name, body = match.group(1), match.group(2)
            keys = set(_PROP_RE.findall(body))
            if keys:
                records[name] = keys
    return records


@pytest.fixture(scope="module")
def csharp_records() -> dict[str, set[str]]:
    return _parse_csharp_records()


@pytest.mark.parametrize("record_name,py_model", sorted(CSHARP_TO_PY.items()))
def test_python_dto_covers_shell_keys(
    csharp_records: dict[str, set[str]],
    record_name: str,
    py_model: type,
) -> None:
    if record_name not in csharp_records:
        pytest.skip(f"{record_name} not present in shell models")

    shell_keys = csharp_records[record_name]
    py_keys = set(py_model.model_fields.keys())
    missing = shell_keys - py_keys
    assert not missing, (
        f"{py_model.__name__} is missing keys the shell expects: {sorted(missing)}. "
        f"Shell keys: {sorted(shell_keys)}; Python keys: {sorted(py_keys)}."
    )
