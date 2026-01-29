from pydantic import BaseModel
from dotenv import load_dotenv
import os

# Load .env once, at import time
load_dotenv()


class Settings(BaseModel):
    app_name: str = "HS Emulator API"
    environment: str = os.getenv("ENV", "development")

    supabase_url: str | None = os.getenv("SUPABASE_URL")
    supabase_service_role_key: str | None = os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY"
    )

    runtime_api_token: str | None = os.getenv("RUNTIME_API_TOKEN")


settings = Settings()
