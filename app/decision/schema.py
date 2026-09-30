"""
app/decision/schema.py

Pydantic model for the structured decision output produced by the Decision Engine.
Every call to engine.classify() returns a validated Decision instance.
"""

from pydantic import field_validator

from app.core.models import OpenVoiceModel
from app.core.types import IntentCategory


class Decision(OpenVoiceModel):
    """Structured output of the Decision Engine.

    Attributes:
        intent: One of the 12 supported intent categories.
        confidence: Calibrated probability [0.0, 1.0] from Laya's RLCD training.
        requires_confirmation: True when the action is potentially irreversible
            or confidence is below the high-confidence threshold.
        entities: Extracted parameters — stub returning {} in PRE-PHASE-0.
            Entity extraction (delta values, file paths, etc.) is Phase 1.
        escalate: True when confidence < 0.4 or intent == "unknown".
            Signals that the orchestrator should not attempt execution.
    """

    intent: str
    confidence: float
    requires_confirmation: bool
    entities: dict[str, object]
    escalate: bool

    @field_validator("intent")
    @classmethod
    def intent_must_be_valid(cls, v: str) -> str:
        valid = {c.value for c in IntentCategory}
        if v not in valid:
            raise ValueError(
                f"intent {v!r} is not a recognised category. "
                f"Valid: {sorted(valid)}"
            )
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v
