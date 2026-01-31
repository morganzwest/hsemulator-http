from __future__ import annotations

import logging
from typing import Any, Dict

from app.services.execution_service import execution_queue
from app.workers.python_worker import run_python_job
from app.workers.node_worker import run_node_job

logger = logging.getLogger(__name__)


async def worker_loop() -> None:
    logger.info("Worker loop started")

    while True:
        job: Dict[str, Any] = await execution_queue.get()
        execution_id = job.get("execution_id")

        try:
            payload = job["payload"]
            lang = payload["config"]["action"]["language"]

            logger.info(
                "Dequeued execution job",
                extra={
                    "execution_id": str(execution_id),
                    "language": lang,
                },
            )

            if lang == "python":
                await run_python_job(execution_id, payload)
            elif lang in ("javascript", "node"):
                await run_node_job(execution_id, payload)
            else:
                raise RuntimeError(f"Unsupported language: {lang}")

            logger.info(
                "Execution job finished",
                extra={
                    "execution_id": str(execution_id),
                    "language": lang,
                },
            )

        except Exception:
            logger.exception(
                "Execution job failed in worker loop",
                extra={"execution_id": str(execution_id)},
            )

        finally:
            execution_queue.task_done()
