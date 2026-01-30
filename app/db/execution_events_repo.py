from __future__ import annotations

from typing import Optional
from uuid import UUID
from datetime import datetime

from app.db.client import get_supabase


def insert_execution_event(
    *,
    execution_fk: UUID,
    kind: str,
    event_time: datetime | str,
    message: Optional[str] = None,
):
    supabase = get_supabase()

    if isinstance(event_time, datetime):
        event_time = event_time.isoformat()

    payload = {
        "execution_fk": str(execution_fk),
        "kind": kind,
        "event_time": event_time,
        "message": message,
    }

    return (
        supabase
        .table("action_execution_events")
        .insert(payload)
        .execute()
    )
