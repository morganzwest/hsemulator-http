from __future__ import annotations

import logging

from app.db.execution_events_repo import insert_execution_event
from app.services.event_mapper import event_to_db_payload
from app.models.events import ExecutionEvent

logger = logging.getLogger(__name__)


class RealtimeDBEventSink:
    def emit(self, event: ExecutionEvent) -> None:
        try:
            kind, message = event_to_db_payload(event)

            insert_execution_event(
                execution_fk=event.execution_id,
                kind=kind,
                event_time=event.ts,
                message=message,
            )

        except Exception:
            # Never let event persistence break execution
            logger.exception(
                "Failed to persist execution event",
                extra={"execution_id": str(event.execution_id)},
            )
