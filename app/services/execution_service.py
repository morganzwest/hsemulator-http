from __future__ import annotations
from typing import Any, Dict
from uuid import UUID

from app.db.executions_repo import update_execution_status, get_execution_by_id
from app.gcp.jobs import run_execution_job
from app.config import settings


async def get_execution_payload(execution_id: UUID) -> Dict[str, Any]:
    execution = get_execution_by_id(execution_id)
    if not execution:
        raise RuntimeError(f"Execution not found: {execution_id}")

    payload = execution.get("payload")
    if payload is None:
        raise RuntimeError(f"Execution payload missing: {execution_id}")

    return payload


async def enqueue_execution_job(
    execution_id: UUID,
    payload: Dict[str, Any],
) -> None:
    update_execution_status(
        execution_id=str(execution_id),
        status="queued",
        payload=payload,
    )

    # ONLY schedule – never execute
    if settings.execution_mode != "local":
        await run_execution_job(execution_id)
