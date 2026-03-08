"""
Route blueprints initialization.

This module imports and registers all API blueprints for the application.
"""

from fastapi import FastAPI

from .core import router as core_router
from .secrets import router as secrets_router
from .cicd import router as cicd_router
from .workflows import router as workflows_router
from .code import router as code_router


def register_blueprints(app: FastAPI):
    """
    Register all blueprints with the FastAPI application.
    
    Args:
        app: FastAPI application instance
    """
    # Register core endpoints (health, execute)
    app.include_router(core_router)
    
    # Register secret management endpoints
    app.include_router(secrets_router)
    
    # Register CI/CD endpoints
    app.include_router(cicd_router)
    
    # Register workflow discovery endpoints
    app.include_router(workflows_router)
    
    # Register code processing endpoints
    app.include_router(code_router)
