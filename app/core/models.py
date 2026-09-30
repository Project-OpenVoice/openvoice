"""
app/core/models.py

Shared Pydantic base models used across both the Decision Engine
and the Memory Manager.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict


class OpenVoiceModel(BaseModel):
    """Base model for all OpenVoice data objects.

    Enforces:
    - Immutable instances (frozen=True) — prevents accidental mutation.
    - No extra fields allowed — catches typos / schema drift early.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


def utcnow() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)
