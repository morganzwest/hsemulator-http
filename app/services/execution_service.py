"""
Execution Service for HSEmulator

This module manages the execution lifecycle of HubSpot workflow actions.
It handles job queuing, payload retrieval, and dispatching to appropriate
execution environments based on the action language.

Key Features:
- Asynchronous job queuing and execution
- Support for local and cloud execution modes
- Language-specific execution dispatch (Python, Node.js)
- Execution status tracking and management

Execution Modes:
- local: Immediate execution for development/testing
- cloud: Job queuing for cloud-based execution

Dependencies:
- Database repositories for execution state management
- GCP jobs service for cloud execution
- Configuration settings for execution mode
"""

from __future__ import annotations
from typing import Any, Dict
from uuid import UUID

from app.db.executions_repo import update_execution_status, get_execution_by_id
from app.gcp.jobs import run_execution_job
from app.config import settings


async def get_execution_payload(execution_id: UUID) -> Dict[str, Any]:
    """
    Retrieve the execution payload for a given execution ID.

    This function fetches the stored execution configuration and payload
    from the database, validating that the execution exists and has
    the required payload data.

    Args:
        execution_id: Unique identifier for the execution

    Returns:
        Dict[str, Any]: Execution payload containing action configuration

    Raises:
        RuntimeError: If execution is not found or payload is missing
    """
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
    """
    Queue an execution job for processing.

    This function updates the execution status to 'queued' and stores
    the payload. In cloud mode, it also schedules the job with the
    GCP jobs service for asynchronous execution.

    Args:
        execution_id: Unique identifier for the execution
        payload: Execution payload containing action configuration
    """
    # Update execution status and store payload
    update_execution_status(
        execution_id=str(execution_id),
        status="queued",
        payload=payload,
    )

    # In cloud mode, schedule job for asynchronous execution
    # In local mode, only queue - execution happens immediately
    if settings.execution_mode != "local":
        await run_execution_job(execution_id)
