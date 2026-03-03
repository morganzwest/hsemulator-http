from __future__ import annotations

import os
from typing import List
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv

# Load .env once, at import time
load_dotenv()


class Settings(BaseModel):
    # ----------------------------
    # Core app
    # ----------------------------
    app_name: str = "HS Emulator API"
    environment: str = os.getenv("ENV", "development")
    execution_mode: str = os.getenv("EXECUTION_MODE", "local")

    # ----------------------------
    # Supabase
    # ----------------------------
    supabase_url: str | None = os.getenv("SUPABASE_URL")
    supabase_service_role_key: str | None = os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY"
    )

    # ----------------------------
    # Auth
    # ----------------------------
    runtime_api_token: str | None = os.getenv("RUNTIME_API_TOKEN")

    # ----------------------------
    # Error Tracking (Sentry/Better Stack)
    # ----------------------------
    sentry_dsn: str | None = os.getenv("SENTRY_DSN")
    sentry_release: str = os.getenv("SENTRY_RELEASE", "0.1.0")
    sentry_environment: str = os.getenv("SENTRY_ENVIRONMENT", "development")
    sentry_traces_sample_rate: float = float(
        os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
    sentry_server_name: str | None = os.getenv("SENTRY_SERVER_NAME")
    sentry_debug: bool = os.getenv("SENTRY_DEBUG", "false").lower() == "true"

    @field_validator("sentry_traces_sample_rate", mode="before")
    @classmethod
    def validate_traces_sample_rate(cls, v):
        try:
            rate = float(v)
            if not 0.0 <= rate <= 1.0:
                raise ValueError("Sample rate must be between 0.0 and 1.0")
            return rate
        except (ValueError, TypeError):
            return 0.1  # default fallback

    # ----------------------------
    # CORS
    # ----------------------------
    # Comma-separated list in env:
    # CORS_ORIGINS=http://localhost:3000,https://app.example.com
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://hsemulator-ui.vercel.app",
        "api.novocode.novocy.com"
    ]

    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = [
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ]
    cors_allow_headers: List[str] = ["*"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """
        Allows env override via comma-separated string.
        """
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


# Instantiate once
settings = Settings(
    cors_origins=os.getenv("CORS_ORIGINS", None)
    or Settings().cors_origins
)
