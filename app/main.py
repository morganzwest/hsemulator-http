"""
Novocode Runtime API - Main FastAPI Application

This module provides the main HTTP API for the Novocode service, which handles
workflow action execution, secret management, and CI/CD operations.

Key Features:
- Workflow action execution with local and cloud modes
- Secure secret storage and retrieval with AES-GCM encryption
- CI/CD integration for HubSpot workflow management
- Comprehensive error tracking with Sentry integration
- Authentication via runtime API tokens

Architecture:
- FastAPI-based REST API with CORS support
- Asynchronous execution with job queuing
- Layered authentication and authorization
- Structured error handling and logging
- Modular blueprint-based route organization

Environment Variables:
- EXECUTION_MODE: 'local' for immediate execution, 'cloud' for job queuing
- RUNTIME_API_TOKEN: Bearer token for API authentication
- SENTRY_DSN: Error tracking configuration
- CORS_ORIGINS: Comma-separated list of allowed origins
"""

from __future__ import annotations

import logging
from os import getenv
from typing import Dict, Any

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from app.config import settings
from app.logger import ExecutionContextFilter, SentryContextFilter
from app.routes import register_blueprints

logger = logging.getLogger(__name__)

# Detect if running in Google Cloud Run environment
IS_CLOUD_RUN = bool(getenv("K_SERVICE"))

# Configure structured logging with execution context
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s "
        "execution_id=%(execution_id)s "
        "status=%(status)s "
        "%(message)s"
    )
)
# Add custom filters for execution tracking and Sentry context
handler.addFilter(ExecutionContextFilter())
handler.addFilter(SentryContextFilter())

logging.basicConfig(level=logging.INFO, handlers=[handler])

# ----------------------------
# Sentry Error Tracking Configuration
# ----------------------------
if settings.sentry_dsn:
    # Configure logging integration for Sentry
    sentry_logging = LoggingIntegration(
        level=logging.INFO,      # Capture INFO and above as breadcrumbs
        event_level=logging.ERROR  # Send ERROR level events to Sentry
    )

    def before_send(event: Dict[str, Any] | None, hint: Dict[str, Any]) -> Dict[str, Any] | None:
        """
        Add custom metadata to Sentry events before sending.

        This function enriches Sentry events with application context
        including execution mode, environment, and service information
        to help with debugging and monitoring.
        """
        if event is None:
            return None

        # Add custom tags for filtering and grouping in Sentry
        event["tags"] = {
            **event.get("tags", {}),
            "execution_mode": settings.execution_mode,
            "is_cloud_run": IS_CLOUD_RUN,
            "service": settings.app_name,
        }

        # Add extra context for detailed debugging information
        event["extra"] = {
            **event.get("extra", {}),
            "environment_info": {
                "environment": settings.environment,
                "execution_mode": settings.execution_mode,
                "is_cloud_run": IS_CLOUD_RUN,
                "app_name": settings.app_name,
            }
        }

        return event

    # Initialize Sentry SDK with comprehensive configuration
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(),  # FastAPI-specific error tracking
            sentry_logging         # Logging integration
        ],
        traces_sample_rate=settings.sentry_traces_sample_rate,  # Performance monitoring
        environment=settings.sentry_environment,
        release=settings.sentry_release,
        server_name=settings.sentry_server_name,
        debug=settings.sentry_debug,
        before_send=before_send,
        attach_stacktrace=True,    # Include stack traces for better debugging
        max_breadcrumbs=50,       # Maximum breadcrumb count for context
    )

    # Set global user context for Sentry (can be overridden per request)
    sentry_sdk.set_user({
        "id": "system",
        "environment": settings.environment,
        "execution_mode": settings.execution_mode,
    })

    # Set global tags for consistent filtering in Sentry
    sentry_sdk.set_tag("service", settings.app_name)
    sentry_sdk.set_tag("execution_mode", settings.execution_mode)
    sentry_sdk.set_tag("is_cloud_run", IS_CLOUD_RUN)

    logger.info("Sentry error tracking initialized", extra={
        "environment": settings.sentry_environment,
        "release": settings.sentry_release,
        "traces_sample_rate": settings.sentry_traces_sample_rate,
    })
else:
    logger.warning("SENTRY_DSN not configured - error tracking disabled")

# Initialize FastAPI application
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

# ----------------------------
# CORS (Cross-Origin Resource Sharing) Configuration
# ----------------------------
# Parse CORS origins from environment variable
# Supports both comma-separated string and list formats
# Example: CORS_ORIGINS="http://localhost:3000,https://app.example.com"
origins = (
    settings.cors_origins
    if isinstance(settings.cors_origins, list)
    else [o.strip() for o in settings.cors_origins.split(",")]
)

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ----------------------------
# Global Exception Handler
# ----------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for all unhandled exceptions.

    This middleware captures unhandled exceptions, adds context to Sentry,
    and returns a standardized error response. It filters sensitive headers
    and includes execution context when available.
    """
    # Add request context to Sentry for better debugging
    if settings.sentry_dsn:
        with sentry_sdk.configure_scope() as scope:
            # Filter sensitive headers to avoid exposing secrets
            safe_headers = {}
            for key, value in request.headers.items():
                if key.lower() not in ['authorization', 'cookie', 'x-api-key', 'x-auth-token']:
                    safe_headers[key] = value

            # Set request context in Sentry
            scope.set_context("request", {
                "url": str(request.url),
                "method": request.method,
                "headers": safe_headers,
                "client": {
                    "host": request.client.host if request.client else None,
                    "port": request.client.port if request.client else None,
                },
                "query_params": dict(request.query_params),
            })

            # Add execution context if available from request state
            if hasattr(request.state, 'execution_id'):
                scope.set_tag("execution_id", request.state.execution_id)
            if hasattr(request.state, 'status'):
                scope.set_tag("status", request.state.status)

        # Capture exception with additional context in Sentry
        sentry_sdk.capture_exception(exc)

    # Sanitize exception message to prevent secret leakage
    error_message = str(exc)

    # Filter out potential secret values from error messages
    sensitive_patterns = [
        'password', 'token', 'secret', 'key', 'credential',
        'authorization', 'bearer', 'api_key'
    ]

    for pattern in sensitive_patterns:
        if pattern.lower() in error_message.lower():
            error_message = f"Internal server error (sensitive information filtered)"
            break

    # Return standardized error response
    return JSONResponse(
        status_code=500,
        content={"error": error_message},
    )


# ----------------------------
# Register Route Blueprints
# ----------------------------
register_blueprints(app)
