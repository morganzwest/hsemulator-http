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
