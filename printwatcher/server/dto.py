"""Pydantic DTOs mirroring the WatcherCore data classes.

Keeping these as a thin adapter (rather than annotating ``PrintOptions``
itself with Pydantic) means ``printwatcher/core.py`` stays Pydantic-free —
the legacy Tk UI doesn't pull FastAPI's deps.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

from printwatcher.core import PrintOptions, PrintRecord

Side = Literal["simplex", "duplex", "duplexshort"]
Color = Literal["color", "monochrome"]


class PrintOptionsDto(BaseModel):
    printer: str | None = None
    copies: int = Field(default=1, ge=1, le=99)
    sides: Side | None = None
    color: Color | None = None

    @classmethod
    def from_core(cls, options: PrintOptions) -> PrintOptionsDto:
        return cls(
            printer=options.printer,
            copies=options.copies,
            sides=options.sides,  # type: ignore[arg-type]
            color=options.color,  # type: ignore[arg-type]
        )

    def to_core(self) -> PrintOptions:
        return PrintOptions(
            printer=self.printer,
            copies=self.copies,
            sides=self.sides,
            color=self.color,
        )


class PrintRecordDto(BaseModel):
    id: str = ""  # derived; stable across reloads (sha1 of timestamp+filename+submitter)
    timestamp: str
    filename: str
    status: str
    detail: str = ""
    printer: str = ""
    copies: int = 1
    sides: str = ""
    color: str = ""
    submitter: str = ""

    @classmethod
    def from_core(cls, record: PrintRecord) -> PrintRecordDto:
        return cls(id=record_id(record), **record.__dict__)


def record_id(record: PrintRecord) -> str:
    """Stable, deterministic id derived from the record's identifying fields.

    Not a security primitive — sha1 is fine here, only used for routing
    /api/history/{id}/reprint to the right entry. Survives process restart
    because the inputs are loaded verbatim from history.json.
    """
    seed = f"{record.timestamp}|{record.filename}|{record.submitter}"
    return hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


class StatsDto(BaseModel):
    printed: int
    today: int
    pending: int
    errors: int


class PendingItemDto(BaseModel):
    path: str
    name: str


class PrintersDto(BaseModel):
    default: str | None
    list: list[str]


class PreferencesDto(BaseModel):
    theme: str = "Ocean"
    hold_mode: bool = False
    larger_text: bool = False
    reduce_transparency: bool = False


class StateDto(BaseModel):
    version: str
    stats: StatsDto
    paused: bool
    options: PrintOptionsDto
    pending: list[PendingItemDto]
    preferences: PreferencesDto
    printers: PrintersDto


class PauseDto(BaseModel):
    paused: bool


class ToolRunDto(BaseModel):
    module: str
    args: list[str] = Field(default_factory=list)
    label: str | None = None


class ToolRunStartedDto(BaseModel):
    run_id: str
    label: str


class VersionDto(BaseModel):
    app: str
    server: str = "fastapi"
    python: str


class UpdateCheckDto(BaseModel):
    current: str
    latest: str | None = None
    html_url: str | None = None
    has_update: bool = False
    checked_at: str | None = None  # ISO timestamp of the last successful poll


class InboxHealthDto(BaseModel):
    watch_dir: str
    inbox_count: int = 0
    inbox_bytes: int = 0
    printed_count: int = 0
    printed_bytes: int = 0
    skipped_count: int = 0
    skipped_bytes: int = 0
    scheduled_count: int = 0
    scheduled_bytes: int = 0
    total_bytes: int = 0
