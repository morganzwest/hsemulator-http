from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from app.services.execution_service import execution_queue
from app.db.executions_repo import update_execution_status


async def worker_loop() -> None:
    while True:
        job: Dict[str, Any] = await execution_queue.get()
        execution_id: str = job["execution_id"]

        start_time = time.perf_counter()

        try:
            # Mark as running
            update_execution_status(
                execution_id=execution_id,
                status="running",
                started=True,
            )

            # Placeholder: later dispatch to python_worker/node_worker
            await asyncio.sleep(0.01)

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            update_execution_status(
                execution_id=execution_id,
                status="executed",
                finished=True,
                ok=True,
                result={
                    "ok": True,
                    "output": {},
                },
                duration_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            update_execution_status(
                execution_id=execution_id,
                status="failed",
                finished=True,
                ok=False,
                error_message=str(e),
                duration_ms=elapsed_ms,
            )

        finally:
            execution_queue.task_done()
