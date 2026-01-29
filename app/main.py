from fastapi import FastAPI

from app.config import settings
from app.models import HealthResponse

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )
