"""
app/decision/engine.py

Public entry point for the Decision Engine.

Usage:
    from app.decision.engine import DecisionEngine

    engine = DecisionEngine()
    decision = await engine.classify("turn up the volume")
    print(decision.intent)      # "system.volume"
    print(decision.confidence)  # 0.94
    print(decision.escalate)    # False
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.decision.laya import LayaAdapter
from app.decision.schema import Decision

logger = get_logger("decision.engine")


class DecisionEngine:
    """Converts natural language into a structured Decision.

    The engine:
    - Delegates classification to the Laya adapter.
    - Guarantees a valid Decision is always returned (never raises).
    - Never executes any action — classification only (Rule R1).

    Instantiate once and reuse; the underlying Laya router is a singleton.
    """

    def __init__(self) -> None:
        self._laya = LayaAdapter()

    async def classify(self, text: str) -> Decision:
        """Classify user text into a structured Decision.

        Args:
            text: Raw user input string (plain text, no voice layer).

        Returns:
            A validated Decision with intent, confidence, entities ({}),
            requires_confirmation, and escalate flags.
        """
        with logger.timed("classify") as ctx:
            decision = await self._laya.classify(text)
            ctx.extra["intent"] = decision.intent
            ctx.extra["confidence"] = decision.confidence
            ctx.extra["escalate"] = decision.escalate
            return decision
