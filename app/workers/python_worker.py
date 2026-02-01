from __future__ import annotations
from app.models.events import (
    ExecutionEvent,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionTimedOut,
)
from typing import Iterable, Optional

import logging
from typing import Any, Dict
from uuid import UUID

from app.shims.python_shim import PythonShim
from app.db.executions_repo import update_execution_status
from app.services.event_sink import RealtimeDBEventSink
from app.services.secret_resolver import resolve_secret_value

logger = logging.getLogger(__name__)


def classify_execution(events: Iterable[ExecutionEvent]) -> tuple[bool, Optional[str]]:
    """
    Returns (ok, error_message)
    """

    # Any hard failure wins
    for ev in reversed(events):
        if isinstance(ev, (ExecutionFailed, ExecutionTimedOut)):
            return False, getattr(ev, "message", "Execution failed")

        # Defensive: completed but explicitly not ok
        if isinstance(ev, ExecutionCompleted) and ev.ok is False:
            return False, "Execution completed with ok=false"

    # Success only if we *actually* completed successfully
    for ev in reversed(events):
        if isinstance(ev, ExecutionCompleted) and ev.ok is True:
            return True, None

    # No terminal signal at all → treat as failure
    return False, "Execution ended without terminal event"


shim = PythonShim(
    timeout_s=15,
    allow_imports=[
        # requests
        "requests",
        "urllib3",
        "idna",
        "certifi",
        "charset_normalizer",

        # hubspot
        "hubspot",
        "six",
        "python_dateutil",
        "dateutil",
        "typing_extensions",

        # google api
        "googleapiclient",
        "google",
        "httplib2",
        "uritemplate",
        "google_auth",
        "google_auth_httplib2",
        "oauth2client",
        "rsa",
        "pyasn1",
        "pyasn1_modules",
        "cachetools",

        # mysql
        "mysql",
        "mysql_connector_python",
        "cryptography",

        # redis
        "redis",
        "async_timeout",

        # nltk
        "nltk",
        "regex",
        "joblib",
        "tqdm",
        "numpy",
        "scipy",
        "sklearn",
    ],
    sink=RealtimeDBEventSink(),
)


async def run_python_job(execution_id: UUID, payload: Dict[str, Any]) -> None:
    logger.info(
        "Starting python execution",
        extra={"execution_id": str(execution_id)},
    )

    # Mark running
    update_execution_status(
        execution_id=execution_id,
        status="running",
        started=True,
    )

    cfg = payload["config"]
    action = cfg["action"]
    fixtures = cfg.get("fixtures", [])

    logger.debug(
        "Loaded execution config",
        extra={
            "execution_id": str(execution_id),
            "entry": action.get("entry"),
            "has_fixtures": bool(fixtures),
        },
    )

    # Locate event.json fixture
    event_source = None
    for f in fixtures:
        if f.get("name") == "event.json":
            event_source = f.get("source")
            break

    if not event_source:
        logger.error(
            "Missing event.json fixture",
            extra={"execution_id": str(execution_id)},
        )

        update_execution_status(
            execution_id=execution_id,
            status="failed",
            finished=True,
            ok=False,
            error_message="Missing event.json fixture",
        )
        return

    logger.info(
        "Invoking Python shim",
        extra={
            "execution_id": str(execution_id),
            "entry": action.get("entry"),
        },
    )

    raw_env = cfg.get("env", {})
    resolved_env: dict[str, str] = {}

    for key, value in raw_env.items():
        if isinstance(value, dict) and value.get("type") == "secret":
            secret_id = (
                value["secret_id"]
                if isinstance(value["secret_id"], UUID)
                else UUID(value["secret_id"])
            )

            logger.debug(
                "Resolving secret env var",
                extra={
                    "execution_id": str(execution_id),
                    "env_key": key,
                    "secret_id": str(secret_id),
                },
            )

            resolved_env[key] = resolve_secret_value(secret_id)
        else:
            if not isinstance(value, str):
                raise ValueError(f"Env var {key} must be string or secret ref")
            resolved_env[key] = value

    # Run shim (events emitted via sink)
    events = await shim.run(
        execution_id=execution_id,
        action_source=action["source"],
        entry=action["entry"],
        event_source=event_source,
        env=resolved_env,
    )

    logger.info(
        "Python shim finished",
        extra={
            "execution_id": str(execution_id),
            "event_count": len(events),
        },
    )

    # Determine final status from terminal event
    ok, error_message = classify_execution(events)

    if ok:
        logger.info(
            "Execution completed successfully",
            extra={"execution_id": str(execution_id)},
        )

        update_execution_status(
            execution_id=execution_id,
            status="completed",
            finished=True,
            ok=True,
            result={"ok": True},  # later: wire ReturnValue
        )
        return

    logger.warning(
        "Execution failed",
        extra={
            "execution_id": str(execution_id),
            "reason": error_message,
        },
    )

    update_execution_status(
        execution_id=execution_id,
        status="failed",
        finished=True,
        ok=False,
        error_message=error_message,
    )
