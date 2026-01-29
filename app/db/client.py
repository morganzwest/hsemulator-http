from supabase import create_client, Client
from app.config import settings

_supabase: Client | None = None


def get_supabase() -> Client:
    global _supabase

    if _supabase is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase environment variables not set")

        _supabase = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    return _supabase
