"""
app/memory/schemas.py

Pydantic models for all memory objects stored and returned by the MemoryManager.
"""

from __future__ import annotations

from datetime import datetime

from app.core.models import OpenVoiceModel, utcnow


class Note(OpenVoiceModel):
    """A markdown note stored in the Obsidian vault."""

    id: str           # slug derived from title, e.g. "meeting-notes"
    title: str
    content: str
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime


class Task(OpenVoiceModel):
    """A structured task stored in SQLite."""

    id: str
    title: str
    completed: bool = False
    due: datetime | None = None
    created_at: datetime
    updated_at: datetime


class Event(OpenVoiceModel):
    """A calendar event stored in SQLite."""

    id: str
    title: str
    start: datetime
    end: datetime | None = None
    description: str = ""
    created_at: datetime
    updated_at: datetime


class SearchResult(OpenVoiceModel):
    """A single result from any search operation (semantic, keyword, or exact)."""

    id: str
    source: str       # "obsidian" | "sqlite.tasks" | "sqlite.events" | "chroma"
    path: str         # file path (obsidian) or table/row reference (sqlite)
    title: str
    snippet: str      # short excerpt for display
    score: float      # relevance score [0.0, 1.0]; higher = more relevant
