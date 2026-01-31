import os
import httpx
import google.auth
from google.auth.transport.requests import Request
from uuid import UUID

GCP_PROJECT = os.environ["GCP_PROJECT"]
GCP_REGION = os.environ["GCP_REGION"]
JOB_NAME = os.environ["WORKER_JOB_NAME"]


def _get_access_token() -> str:
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(Request())
    return credentials.token


async def run_execution_job(execution_id: UUID) -> None:
    url = (
        f"https://{GCP_REGION}-run.googleapis.com"
        f"/apis/run.googleapis.com/v1"
        f"/projects/{GCP_PROJECT}"
        f"/locations/{GCP_REGION}"
        f"/jobs/{JOB_NAME}:run"
    )

    token = _get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

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
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()
