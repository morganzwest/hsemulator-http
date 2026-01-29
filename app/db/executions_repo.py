from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from app.models.errors import ExecutionNotFoundError
from app.db.client import get_supabase

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def update_execution_status(
    *,
    execution_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
    ok: bool | None = None,
    started: bool = False,
    finished: bool = False,
    duration_ms: int | None = None,
):
    supabase = get_supabase()

    update: dict[str, Any] = {
        "status": status,
    }

    if started:
        update["started_at"] = _iso_now()

    if finished:
        update["finished_at"] = _iso_now()

    if duration_ms is not None:
        update["duration_ms"] = duration_ms

    if result is not None:
        update["result"] = result

    if error_message is not None:
        update["error_message"] = error_message

    if ok is not None:
        update["ok"] = ok

    logger.info(
        "Updating execution status",
        extra={
            "execution_id": execution_id,
            "status": status,
            "started": started,
            "finished": finished,
            "ok": ok,
            "has_result": result is not None,
        },
    )

    try:
        response = (
            supabase
            .table("action_executions")
            .update(update)
            .eq("id", execution_id)
            .execute()
        )
        if not response.data:
            logger.warning(
                "Execution not found",
                extra={
                    "execution_id": execution_id,
                    "status": status,
                },
            )
            raise ExecutionNotFoundError(execution_id)

        logger.debug(
            "Execution status updated successfully",
            extra={
                "execution_id": execution_id,
                "status": status,
                "rows_affected": len(response.data) if response.data else 0,
            },
        )

        return response

    except Exception:
        logger.exception(
            "Failed to update execution status",
            extra={
                "execution_id": execution_id,
                "status": status,
            },
        )
        raise
