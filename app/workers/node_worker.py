from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from app.shims.node_shim import NodeShim
from app.db.executions_repo import update_execution_status
from app.services.event_sink import RealtimeDBEventSink
from app.services.secret_resolver import resolve_secret_value

logger = logging.getLogger(__name__)


shim = NodeShim(
    timeout_s=15,
    sink=RealtimeDBEventSink(),
)


async def run_node_job(execution_id: UUID, payload: Dict[str, Any]) -> None:
    logger.info(
        "Starting node execution",
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

    # Resolve env vars (identical to python_worker)
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

    logger.info(
        "Invoking Node shim",
        extra={
            "execution_id": str(execution_id),
            "entry": action.get("entry"),
        },
    )

    events = await shim.run(
        execution_id=execution_id,
        action_source=action["source"],
        entry=action.get("entry", "action.js"),
        event_source=event_source,
        env=resolved_env,
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
            result={"ok": True},
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
