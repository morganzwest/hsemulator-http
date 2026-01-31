import google.auth
from google.auth.transport.requests import Request
from uuid import UUID
import httpx
import os

GCP_PROJECT = os.environ["GCP_PROJECT"]
GCP_REGION = os.environ["GCP_REGION"]
JOB_NAME = os.environ["WORKER_JOB_NAME"]


async def run_execution_job(execution_id: UUID) -> None:
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(Request())

    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }

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
        response = await client.post(url, json=body, headers=headers)
        response.raise_for_status()
