from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from app.workers.python_worker import run_python_job
from app.workers.node_worker import run_node_job
from app.services.execution_service import get_execution_payload
from app.db.executions_repo import update_execution_status
import time

logger = logging.getLogger(__name__)


async def run_execution(execution_id: UUID) -> None:
    start = time.monotonic()

    update_execution_status(
        execution_id=str(execution_id),
        status="running",
        started=True,
    )

    try:
        payload = await get_execution_payload(execution_id)
        lang = payload["config"]["action"]["language"]

        if lang == "python":
            await run_python_job(execution_id, payload)
        elif lang in ("javascript", "node"):
            await run_node_job(execution_id, payload)
        else:
            raise RuntimeError(f"Unsupported language: {lang}")

        duration_ms = int((time.monotonic() - start) * 1000)

        update_execution_status(
            execution_id=str(execution_id),
            status="completed",
            ok=True,
            finished=True,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)

        update_execution_status(
            execution_id=str(execution_id),
            status="failed",
            ok=False,
            finished=True,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise
