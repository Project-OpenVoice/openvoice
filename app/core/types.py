"""
app/core/types.py

Type aliases and intent category enum used across the entire codebase.
"""

from enum import StrEnum


class IntentCategory(StrEnum):
    """All supported intent categories for PRE-PHASE-0."""

    SYSTEM_VOLUME = "system.volume"
    SYSTEM_BRIGHTNESS = "system.brightness"
    SYSTEM_MEDIA_SPOTIFY = "system.media.spotify"
    SYSTEM_MEDIA_YOUTUBE = "system.media.youtube"
    SYSTEM_FILE_OPEN = "system.file.open"
    SYSTEM_FILE_SEARCH = "system.file.search"
    MEMORY_NOTE_CREATE = "memory.note.create"
    MEMORY_NOTE_SEARCH = "memory.note.search"
    CALENDAR_EVENT_CREATE = "calendar.event.create"
    CALENDAR_EVENT_SEARCH = "calendar.event.search"
    GENERAL_CHAT = "general.chat"
    UNKNOWN = "unknown"


# Intents that require explicit user confirmation before execution.
CONFIRMATION_REQUIRED_INTENTS: frozenset[str] = frozenset(
    {
        IntentCategory.SYSTEM_FILE_OPEN,  # could open wrong file
    }
)

# Confidence below which escalation is triggered.
ESCALATION_CONFIDENCE_THRESHOLD: float = 0.4

# Type aliases
Json = dict[str, object]
