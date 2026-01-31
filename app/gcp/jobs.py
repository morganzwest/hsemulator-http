import os
import httpx
from uuid import UUID
from typing import Dict, Any

GCP_PROJECT = os.environ["GCP_PROJECT"]
GCP_REGION = os.environ["GCP_REGION"]
JOB_NAME = os.environ["WORKER_JOB_NAME"]


async def run_execution_job(
    execution_id: UUID,
) -> None:
    """
    Triggers a Cloud Run Job execution.
    """

    url = (
        f"https://{GCP_REGION}-run.googleapis.com"
        f"/apis/run.googleapis.com/v1"
        f"/projects/{GCP_PROJECT}"
        f"/locations/{GCP_REGION}"
        f"/jobs/{JOB_NAME}:run"
    )

    body = {
        "overrides": {
            "containerOverrides": [
                {
                    "env": [
                        {
                            "name": "EXECUTION_ID",
                            "value": str(execution_id),
                        }
                    ]
                }
            ]
        }
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=body)
        response.raise_for_status()
