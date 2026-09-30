"""
app/core/logging.py

Structured JSON logger used by all modules.

Every log line emits:
  - timestamp (ISO 8601)
  - module
  - action
  - duration_ms
  - success
  - (optional extra fields)

Usage:
    from app.core.logging import get_logger
    logger = get_logger(__name__)

    with logger.timed("create_note", module="memory") as ctx:
        ...  # do work
        ctx.extra["note_id"] = note_id
"""

import json
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generator


@dataclass
class _TimedContext:
    """Mutable context passed into a timed block for adding extra metadata."""

    extra: dict[str, Any] = field(default_factory=dict)


class StructuredLogger:
    """Emits one-line JSON log entries to stdout."""

    def __init__(self, module: str) -> None:
        self._module = module

    def _emit(
        self,
        action: str,
        duration_ms: float,
        success: bool,
        **extra: Any,
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "module": self._module,
            "action": action,
            "duration_ms": round(duration_ms, 2),
            "success": success,
            **extra,
        }
        print(json.dumps(record), file=sys.stdout, flush=True)

    @contextmanager
    def timed(
        self,
        action: str,
        module: str | None = None,
        **static_extra: Any,
    ) -> Generator[_TimedContext, None, None]:
        """Context manager that logs duration and success/failure automatically.

        Example::

            with logger.timed("classify", module="decision") as ctx:
                result = engine.classify(text)
                ctx.extra["intent"] = result.intent
        """
        ctx = _TimedContext()
        start = time.perf_counter()
        success = False
        try:
            yield ctx
            success = True
        except Exception:
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            effective_module = module or self._module
            self._emit(
                action,
                duration_ms,
                success,
                **{**static_extra, **ctx.extra},
            )

    def info(self, action: str, **extra: Any) -> None:
        """Log a one-shot informational entry (no duration)."""
        self._emit(action, duration_ms=0.0, success=True, **extra)

    def error(self, action: str, error: str, **extra: Any) -> None:
        """Log a failure entry."""
        self._emit(action, duration_ms=0.0, success=False, error=error, **extra)


def get_logger(module: str) -> StructuredLogger:
    """Return a StructuredLogger for the given module name."""
    return StructuredLogger(module)
