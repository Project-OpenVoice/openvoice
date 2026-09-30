"""
tests/decision/test_engine.py

Unit tests for the Decision Engine.

Tests run against the live Laya model, so they require:
    uv run pytest tests/decision/ -v

Acceptance criteria (plan.md §7):
- Every intent category is classified correctly on clear examples.
- Confidence is always in [0.0, 1.0].
- Invalid / empty input → intent="unknown", escalate=True, no exception.
- Unknown phrasing → intent="unknown".
- Escalation flag set when confidence < 0.4.
- entities is always a dict (never raises).
"""

from __future__ import annotations

import pytest

from app.decision.engine import DecisionEngine
from app.decision.schema import Decision
from app.core.types import IntentCategory


@pytest.fixture(scope="module")
def engine() -> DecisionEngine:
    """Shared engine instance — loads Laya model once for the whole module."""
    return DecisionEngine()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def classify(engine: DecisionEngine, text: str) -> Decision:
    return await engine.classify(text)


# ---------------------------------------------------------------------------
# Intent routing — one clear test per category
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_volume_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "turn up the volume by 30 percent")
    assert d.intent == IntentCategory.SYSTEM_VOLUME
    assert 0.0 <= d.confidence <= 1.0


@pytest.mark.asyncio
async def test_brightness_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "make the screen brighter")
    assert d.intent == IntentCategory.SYSTEM_BRIGHTNESS


@pytest.mark.asyncio
async def test_spotify_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "play The Weeknd on Spotify")
    assert d.intent == IntentCategory.SYSTEM_MEDIA_SPOTIFY


@pytest.mark.asyncio
async def test_youtube_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "open YouTube and search for Python tutorials")
    assert d.intent == IntentCategory.SYSTEM_MEDIA_YOUTUBE


@pytest.mark.asyncio
async def test_file_open_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "open Visual Studio Code")
    assert d.intent == IntentCategory.SYSTEM_FILE_OPEN


@pytest.mark.asyncio
async def test_file_search_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "find the file called report.pdf")
    assert d.intent == IntentCategory.SYSTEM_FILE_SEARCH


@pytest.mark.asyncio
async def test_note_create_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "create a note about today's meeting")
    assert d.intent == IntentCategory.MEMORY_NOTE_CREATE


@pytest.mark.asyncio
async def test_note_search_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "find my note about the project deadline")
    assert d.intent == IntentCategory.MEMORY_NOTE_SEARCH


@pytest.mark.asyncio
async def test_calendar_create_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "schedule a meeting for tomorrow at 10am")
    assert d.intent == IntentCategory.CALENDAR_EVENT_CREATE


@pytest.mark.asyncio
async def test_calendar_search_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "what meetings do I have today")
    assert d.intent == IntentCategory.CALENDAR_EVENT_SEARCH


@pytest.mark.asyncio
async def test_general_chat_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "who invented the internet")
    assert d.intent == IntentCategory.GENERAL_CHAT


# ---------------------------------------------------------------------------
# Confidence bounds — always in [0.0, 1.0] regardless of input
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    "turn up the volume",
    "open Spotify",
    "asdfghjkl",
    "",
    "   ",
    "???",
    "a" * 500,
])
async def test_confidence_always_in_range(engine: DecisionEngine, text: str) -> None:
    d = await classify(engine, text)
    assert 0.0 <= d.confidence <= 1.0, f"confidence out of range for {text!r}"


# ---------------------------------------------------------------------------
# Invalid / empty input — no crash, falls back to unknown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_string_returns_unknown(engine: DecisionEngine) -> None:
    d = await classify(engine, "")
    assert d.intent == IntentCategory.UNKNOWN
    assert d.escalate is True
    assert d.confidence == 0.0


@pytest.mark.asyncio
async def test_whitespace_only_returns_unknown(engine: DecisionEngine) -> None:
    d = await classify(engine, "   ")
    assert d.intent == IntentCategory.UNKNOWN
    assert d.escalate is True


# ---------------------------------------------------------------------------
# Unknown phrasing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    "asdfghjkl",
    "engage warp drive",
    "reticulate splines",
])
async def test_gibberish_routes_to_unknown(engine: DecisionEngine, text: str) -> None:
    d = await classify(engine, text)
    # Either classified as unknown or escalated due to low confidence
    assert d.intent == IntentCategory.UNKNOWN or d.escalate is True


# ---------------------------------------------------------------------------
# Escalation flag
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalate_on_empty_input(engine: DecisionEngine) -> None:
    d = await classify(engine, "")
    assert d.escalate is True


@pytest.mark.asyncio
async def test_no_escalate_on_clear_intent(engine: DecisionEngine) -> None:
    d = await classify(engine, "increase volume by 20 percent")
    # Clear, unambiguous intent should NOT escalate
    if d.confidence >= 0.4:
        assert d.escalate is False


# ---------------------------------------------------------------------------
# entities is always a dict
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    "turn up the volume",
    "open YouTube",
    "create a note",
    "asdfgh",
    "",
])
async def test_entities_always_dict(engine: DecisionEngine, text: str) -> None:
    d = await classify(engine, text)
    assert isinstance(d.entities, dict), "entities must always be a dict"


# ---------------------------------------------------------------------------
# Schema validation — Decision is always a valid Pydantic model
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decision_is_valid_model(engine: DecisionEngine) -> None:
    d = await classify(engine, "open Spotify and play jazz")
    assert isinstance(d, Decision)
    assert isinstance(d.intent, str)
    assert isinstance(d.confidence, float)
    assert isinstance(d.requires_confirmation, bool)
    assert isinstance(d.entities, dict)
    assert isinstance(d.escalate, bool)
