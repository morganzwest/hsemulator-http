from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from app.shims.python_shim import PythonShim
from app.db.executions_repo import update_execution_status
from app.services.event_sink import RealtimeDBEventSink

logger = logging.getLogger(__name__)


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

    # Run shim (events emitted via sink)
    events = await shim.run(
        execution_id=execution_id,
        action_source=action["source"],
        entry=action["entry"],
        event_source=event_source,
        env=cfg.get("env", {}),
    )

    logger.info(
        "Python shim finished",
        extra={
            "execution_id": str(execution_id),
            "event_count": len(events),
        },
    )

    # Determine final status from terminal event
    last = events[-1] if events else None

    if last and getattr(last, "type", "") == "execution.completed":
        logger.info(
            "Execution completed successfully",
            extra={"execution_id": str(execution_id)},
        )

        update_execution_status(
            execution_id=execution_id,
            status="completed",
            finished=True,
            ok=True,
            result={"ok": True},  # replace later with structured return
        )
        return

    # Failure path
    msg = "Execution failed"
    for ev in reversed(events):
        if getattr(ev, "type", "") in ("execution.failed", "execution.timed_out"):
            if hasattr(ev, "message"):
                msg = ev.message
            break

    logger.warning(
        "Execution failed",
        extra={
            "execution_id": str(execution_id),
            "reason": msg,
        },
    )

    update_execution_status(
        execution_id=execution_id,
        status="failed",
        finished=True,
        ok=False,
        error_message=msg,
    )
