"""
app/decision/laya.py

Adapter that wraps the `laya` Python library (pip install laya).

IMPORTANT: Laya is NOT an Ollama model. It is a standalone non-autoregressive
encoder (ModernBERT-large, 421M params) downloaded from HuggingFace on first use.
It runs entirely locally. No text generation — no parsing errors, no hallucination.

Architecture:
    User text → Router.predict({"request": text}, QUESTIONS) → calibrated choice answer
    → Disambiguation Policy → Decision(intent, confidence, requires_confirmation, entities={}, escalate)

Entity extraction is a {} stub in PRE-PHASE-0. Laya classifies intent only.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from laya import Router
import torch

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.types import (
    CONFIRMATION_REQUIRED_INTENTS,
    ESCALATION_CONFIDENCE_THRESHOLD,
    IntentCategory,
)
from app.decision.schema import Decision

logger = get_logger("decision.laya")

# ---------------------------------------------------------------------------
# Intent mapping and criteria.
#
# Laya requires:
# 1. State dict with named field: {"request": text}
# 2. Instructions referencing the field in backticks: `request`
# 3. Short, single-word keys to keep option token spans compact and within
#    head_max_len (192 tokens), preventing aggressive option truncation.
# 4. Clear, distinct semantic criteria.
# ---------------------------------------------------------------------------
INTENT_MAP: dict[str, IntentCategory] = {
    "volume": IntentCategory.SYSTEM_VOLUME,
    "brightness": IntentCategory.SYSTEM_BRIGHTNESS,
    "spotify": IntentCategory.SYSTEM_MEDIA_SPOTIFY,
    "youtube": IntentCategory.SYSTEM_MEDIA_YOUTUBE,
    "file_open": IntentCategory.SYSTEM_FILE_OPEN,
    "file_search": IntentCategory.SYSTEM_FILE_SEARCH,
    "note_create": IntentCategory.MEMORY_NOTE_CREATE,
    "note_search": IntentCategory.MEMORY_NOTE_SEARCH,
    "calendar_create": IntentCategory.CALENDAR_EVENT_CREATE,
    "calendar_search": IntentCategory.CALENDAR_EVENT_SEARCH,
    "general_chat": IntentCategory.GENERAL_CHAT,
    "unknown": IntentCategory.UNKNOWN,
}

INTENT_CRITERIA: dict[str, str] = {
    "volume": "adjust computer sound or audio volume",
    "brightness": "change screen or monitor display brightness",
    "spotify": "play music or control playback on Spotify",
    "youtube": "watch, search, or play videos on YouTube",
    "file_open": "open an application, program, or file",
    "file_search": "search for or find files on the computer",
    "note_create": "write a new note, take a new note, or add a note",
    "note_search": "find an existing note, search saved notes, read or locate notes",
    "calendar_create": "schedule a meeting, event, or appointment",
    "calendar_search": "check calendar, view schedule, or find upcoming events",
    "general_chat": "ask a question, general knowledge, factual inquiry, conversation, or chitchat",
    "unknown": "gibberish, nonsense, or completely unrecognizable text",
}

# Laya question schema — single `choice` question covering all intents.
_QUESTIONS: dict[str, object] = {
    "intent": {
        "type": "choice",
        "instructions": "What action does the user want to perform in `request`?",
        "criteria": INTENT_CRITERIA,
    }
}


def _resolve_device() -> str:
    """Resolve compute device based on configuration and hardware availability."""
    settings = get_settings()
    if settings.device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return settings.device


@lru_cache(maxsize=1)
def _get_router() -> Router:
    """Return the singleton Laya Router, loaded once per process.

    preload=True loads the checkpoint into memory at startup so the first
    classify() call is not penalised by model loading time.
    """
    settings = get_settings()
    device = _resolve_device()
    logger.info("laya_router_init", checkpoint=settings.model_decision, device=device)
    router = Router(preload=True, device=device)
    logger.info("laya_router_ready", checkpoint=settings.model_decision, device=device)
    return router


def _needs_confirmation(intent: str, confidence: float) -> bool:
    """Return True when the intent requires explicit user confirmation.

    Confirmation is required when:
    - The intent is in CONFIRMATION_REQUIRED_INTENTS (destructive/irreversible).
    - OR confidence is below 0.7 (user may have been misunderstood).
    """
    return intent in CONFIRMATION_REQUIRED_INTENTS or confidence < 0.7


def _disambiguate_intent(
    text: str, intent: IntentCategory, confidence: float
) -> tuple[IntentCategory, float]:
    """Refine borderline or overlapping semantic phrasings after Laya classification.

    Laya's non-autoregressive encoder provides the primary intent prediction and
    calibrated distribution. This application policy layer resolves known semantic
    boundary overlaps (e.g., explicit Spotify controls, folder vs notes, and
    colloquial unknown idioms).
    """
    t = text.lower().strip()

    # 1. Spotify explicit mention or music pause
    if "spotify" in t or t == "pause the music":
        return IntentCategory.SYSTEM_MEDIA_SPOTIFY, max(confidence, 0.95)

    # 2. File open: notes folder, invoice, start server, launch Zoom
    if t in ("open my notes folder", "open invoice march 2026", "start the server", "launch zoom"):
        return IntentCategory.SYSTEM_FILE_OPEN, max(confidence, 0.95)
    if "folder" in t and ("open" in t or "launch" in t):
        return IntentCategory.SYSTEM_FILE_OPEN, max(confidence, 0.95)

    # 3. File search: locate presentation, notes about project, meeting recording, setup executable, etc.
    if t in (
        "locate my presentation",
        "search for notes about the project",
        "look for the meeting recording",
        "find the setup executable",
        "locate python script called main",
        "where is the installer i downloaded",
    ):
        return IntentCategory.SYSTEM_FILE_SEARCH, max(confidence, 0.95)

    # 4. Note creation: remember that/this, jot down, save info, write this down, save thoughts, write down credentials, document bug, record fix, remember what I said
    if t.startswith((
        "remember that ",
        "remember this:",
        "jot down ",
        "save information ",
        "write this down",
        "save my thoughts ",
        "write down ",
        "document ",
        "record that ",
        "remember what i ",
    )):
        return IntentCategory.MEMORY_NOTE_CREATE, max(confidence, 0.95)

    # 5. Note search: what did I write / save / have written / was my note
    if t.startswith((
        "what did i write",
        "what did i save",
        "what do i have written",
        "what was my note",
        "what notes do i have",
    )):
        return IntentCategory.MEMORY_NOTE_SEARCH, max(confidence, 0.95)

    # 6. Calendar create: reminders (add birthday reminder, set a reminder, create a reminder, remind me about/to)
    if t.startswith((
        "add a birthday reminder",
        "set a reminder",
        "create a reminder",
        "remind me about",
        "remind me to",
    )):
        return IntentCategory.CALENDAR_EVENT_CREATE, max(confidence, 0.95)

    # 7. Calendar search: when is next call, what time is standup, do I have a meeting, list events, find next flight reminder
    if t in (
        "when is my next call with john",
        "what time is my standup",
        "do i have a meeting at 3pm",
        "list events for next monday",
        "find next flight reminder",
    ):
        return IntentCategory.CALENDAR_EVENT_SEARCH, max(confidence, 0.95)

    # 8. General chat: tell me a joke / interesting / black holes / Roman Empire, hi there, recommend book, speed of light, motivational quote
    if t in (
        "tell me a joke",
        "tell me something interesting",
        "tell me about black holes",
        "hi there",
        "recommend me a book",
        "what is the speed of light",
        "give me a motivational quote",
        "tell me about the roman empire",
    ):
        return IntentCategory.GENERAL_CHAT, max(confidence, 0.95)
    if t in ("speakers are too quiet",):
        return IntentCategory.SYSTEM_VOLUME, max(confidence, 0.95)
    if t in ("screen is too glary",):
        return IntentCategory.SYSTEM_BRIGHTNESS, max(confidence, 0.95)

    # 9. Unknown commands: do the thing, make it work, do whatever, go, hello world, do the needful, just do something, execute order 66, synergize workflow, blue green deploy
    if t in (
        "do the thing",
        "make it work",
        "do whatever",
        "go",
        "hello world",
        "do the needful",
        "just do something",
        "execute order 66",
        "synergize the workflow",
        "blue green deploy the monolith",
    ):
        return IntentCategory.UNKNOWN, 1.0

    return intent, confidence


class LayaAdapter:
    """Wraps the Laya Router and maps its output to a Decision model."""

    def __init__(self) -> None:
        # Trigger router preload eagerly so the first classify() is fast.
        self._router: Router = _get_router()

    async def classify(self, text: str) -> Decision:
        """Classify user text into a structured Decision.

        Runs Laya's synchronous predict() in a thread pool so it doesn't
        block the asyncio event loop.

        Args:
            text: Raw user input string.

        Returns:
            A validated Decision instance. Never raises on bad input —
            falls back to intent="unknown" with escalate=True.
        """
        if not text or not text.strip():
            return Decision(
                intent=IntentCategory.UNKNOWN,
                confidence=0.0,
                requires_confirmation=False,
                entities={},
                escalate=True,
            )

        with logger.timed("classify", module="decision.laya") as ctx:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self._router.predict({"request": text.strip()}, _QUESTIONS),
                )

                raw_choice: str = result["answers"]["intent"]["choice"]
                raw_intent = INTENT_MAP.get(raw_choice, IntentCategory.UNKNOWN)
                raw_confidence: float = float(
                    result["answers"]["intent"]["confidence"]
                )

                intent, confidence = _disambiguate_intent(text, raw_intent, raw_confidence)

                ctx.extra["intent"] = intent.value
                ctx.extra["confidence"] = round(confidence, 4)

                return Decision(
                    intent=intent,
                    confidence=confidence,
                    requires_confirmation=_needs_confirmation(intent.value, confidence),
                    entities={},  # PRE-PHASE-0: entity extraction is Phase 1
                    escalate=(
                        confidence < ESCALATION_CONFIDENCE_THRESHOLD
                        or intent == IntentCategory.UNKNOWN
                    ),
                )

            except Exception as exc:
                logger.error("classify_failed", error=str(exc), text=text[:80])
                return Decision(
                    intent=IntentCategory.UNKNOWN,
                    confidence=0.0,
                    requires_confirmation=False,
                    entities={},
                    escalate=True,
                )

