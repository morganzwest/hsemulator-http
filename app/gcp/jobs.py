from google.cloud.run_v2.services.jobs import JobsAsyncClient
from google.cloud.run_v2.types import RunJobRequest
from uuid import UUID
import os

GCP_PROJECT = os.environ["GCP_PROJECT"]
GCP_REGION = os.environ["GCP_REGION"]
JOB_NAME = os.environ["WORKER_JOB_NAME"]


async def run_execution_job(execution_id: UUID) -> None:
    client = JobsAsyncClient()

    job_name = (
        f"projects/{GCP_PROJECT}/"
        f"locations/{GCP_REGION}/"
        f"jobs/{JOB_NAME}"
    )

    request = RunJobRequest(
        name=job_name,
        overrides={
            "container_overrides": [
                {
                    "env": [
                        {
                            "name": "EXECUTION_ID",
                            "value": str(execution_id),
                        }
                    ]
                }
            ]
        },
    )

    # Fire-and-forget trigger
    await client.run_job(request=request)
