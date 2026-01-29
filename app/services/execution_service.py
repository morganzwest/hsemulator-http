from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.db.executions_repo import update_execution_status


# In-memory queue for now. Swap later for Redis / Cloud Tasks / SQS.
execution_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()


async def enqueue_execution_job(execution_id: str, payload: Dict[str, Any]) -> None:
    # Persist status first (best-effort)
    update_execution_status(
        execution_id=execution_id,
        status="running",
        started=True,
    )

    # Enqueue job for workers
    await execution_queue.put(
        {
            "execution_id": execution_id,
            "payload": payload,
        }
    )
