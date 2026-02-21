from fastapi import HTTPException, status


class SecretError(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


class SecretScopeViolationError(SecretError):
    pass


class SecretAlreadyExistsError(SecretError):
    def __init__(self, detail: str = "Secret already exists for this scope"):
        super().__init__(detail, status.HTTP_409_CONFLICT)


class SecretPersistenceError(SecretError):
    def __init__(self, detail: str = "Failed to persist secret"):
        super().__init__(detail, status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExecutionNotFoundError(Exception):
    def __init__(self, execution_id: str):
        super().__init__(f"Execution not found: execution_id={execution_id}")
        self.execution_id = execution_id

class SecretNotFoundError(SecretError):
    def __init__(self, detail: str = "Secret not found"):
        super().__init__(detail, status.HTTP_404_NOT_FOUND)

class SecretPortalMismatchError(SecretError):
    def __init__(self, detail: str = "Portal mismatch"):
        super().__init__(detail, status.HTTP_403_FORBIDDEN)

class SecretForbiddenError(SecretError):
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(detail, status.HTTP_403_FORBIDDEN)


class CicdSecretValidationError(SecretError):
    """Base exception for CICD secret validation failures"""
    def __init__(self, detail: str = "CICD secret validation failed"):
        super().__init__(detail, status.HTTP_400_BAD_REQUEST)


class CicdTokenInvalidError(SecretError):
    """Raised when CICD token is invalid (401 response)"""
    def __init__(self, detail: str = "Invalid CICD token: authentication failed"):
        super().__init__(detail, status.HTTP_401_UNAUTHORIZED)


class CicdTokenMissingScopesError(SecretError):
    """Raised when CICD token lacks required scopes (403 response)"""
    def __init__(self, detail: str = "CICD token missing required HubSpot API scopes"):
        super().__init__(detail, status.HTTP_403_FORBIDDEN)
