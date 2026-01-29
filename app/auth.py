from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings

security = HTTPBearer(auto_error=False)


def require_runtime_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if settings.runtime_api_token is None:
        raise RuntimeError("RUNTIME_API_TOKEN not configured")

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid auth scheme",
        )

    if credentials.credentials != settings.runtime_api_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token",
        )

    return True
