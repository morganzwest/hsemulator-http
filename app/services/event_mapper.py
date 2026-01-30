from __future__ import annotations

import json
from typing import Optional

from app.models.events import (
    ExecutionEvent,
    StdoutEmitted,
    StderrEmitted,
    ExecutionFailed,
    ExecutionTimedOut,
    ExecutionStarted,
    ExecutionCompleted,
    ReturnValue,
)


def event_to_db_payload(event: ExecutionEvent) -> tuple[str, Optional[str]]:
    """
    Returns (kind, message)
    Enum labels MUST exactly match execution_event_kind
    """

    if isinstance(event, StdoutEmitted):
        return "Stdout", event.line

    if isinstance(event, StderrEmitted):
        return "Stderr", event.line

    if isinstance(event, ExecutionStarted):
        return "ExecutionStarted", None

    if isinstance(event, ExecutionCompleted):
        return "ExecutionCompleted", None

    if isinstance(event, ExecutionFailed):
        return "ExecutionFailed", event.message

    if isinstance(event, ExecutionTimedOut):
        return "ExecutionTimedOut", f"Timed out after {event.timeout_s}s"

    if isinstance(event, ReturnValue):
        return "Return", json.dumps(event.value)

    # Should never happen
    return "Unknown", json.dumps(event.model_dump())
