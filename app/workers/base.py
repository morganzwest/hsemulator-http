"""
Base Worker Module for HSEmulator Execution

This module provides the core execution orchestration for workflow actions.
It handles the complete execution lifecycle including status management,
language-specific dispatch, error handling, and duration tracking.

Execution Flow:
1. Update execution status to 'running' and record start time
2. Retrieve execution payload with action configuration
3. Dispatch to appropriate language-specific worker
4. Update execution status to 'completed' or 'failed' with duration

Supported Languages:
- Python: Executes Python workflow actions
- JavaScript/Node: Executes Node.js workflow actions

Error Handling:
- Comprehensive exception capture and logging
- Status updates for failed executions
- Duration tracking for all executions
- Error context preservation for debugging

Performance Monitoring:
- Monotonic timing for accurate duration measurement
- Status tracking throughout execution lifecycle
- Structured logging for observability
"""

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
    """
    Execute a workflow action with comprehensive lifecycle management.

    This function orchestrates the complete execution of a workflow action,
    including status updates, language dispatch, and error handling. It
    provides timing information and maintains execution state throughout
    the process.

    Args:
        execution_id: Unique identifier for the execution

    Raises:
        RuntimeError: If unsupported language is specified
        Exception: Propagates execution errors from language workers
    """
    start = time.monotonic()

    try:
        # Retrieve execution payload with action configuration first
        payload = await get_execution_payload(execution_id)
        lang = payload["config"]["action"]["language"]

        # Update execution status to indicate execution has started
        update_execution_status(
            execution_id=str(execution_id),
            status="running",
            started=True,
        )

        # Dispatch to appropriate language-specific worker
        if lang == "python":
            await run_python_job(execution_id, payload)
        elif lang in ("javascript", "node"):
            await run_node_job(execution_id, payload)
        else:
            raise RuntimeError(f"Unsupported language: {lang}")

        # Calculate execution duration and mark as completed
        duration_ms = int((time.monotonic() - start) * 1000)

        update_execution_status(
            execution_id=str(execution_id),
            status="completed",
            ok=True,
            finished=True,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        # Calculate duration and mark as failed
        duration_ms = int((time.monotonic() - start) * 1000)

        # Update status to failed if execution started
        try:
            update_execution_status(
                execution_id=str(execution_id),
                status="failed",
                ok=False,
                finished=True,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
        except Exception as status_exc:
            # If status update fails, log the error but still raise original exception
            logger.error(
                "Failed to update execution status after execution failure",
                extra={
                    "execution_id": str(execution_id),
                    "status_error": str(status_exc),
                    "original_error": str(exc),
                },
            )

        # Re-raise exception for upstream error handling
        raise exc
