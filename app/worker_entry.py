# app/worker_entry.py
import logging
import os
import asyncio
from uuid import UUID

from app.workers.base import run_execution

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def main() -> None:
    execution_id = UUID(os.environ["EXECUTION_ID"])
    logging.info(f"Worker started for execution {execution_id}")
    asyncio.run(run_execution(execution_id))


if __name__ == "__main__":
    main()
