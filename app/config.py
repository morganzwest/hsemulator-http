from pydantic import BaseModel
import os


class Settings(BaseModel):
    app_name: str = "HS Emulator API"
    environment: str = os.getenv("ENV", "development")
    supabase_url: str = os.getenv("SUPABASE_URL")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


settings = Settings()
