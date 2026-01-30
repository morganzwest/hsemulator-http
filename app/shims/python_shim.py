from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.models.events import (
    ExecutionCompleted,
    ExecutionEvent,
    ExecutionFailed,
    ExecutionStarted,
    ExecutionTimedOut,
    ReturnValue,
    StderrEmitted,
    StdoutEmitted,
)

SAFE_BASE_ENV = {
    "PYTHONUNBUFFERED": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}

# -----------------------------
# Safety: env isolation + denylist
# -----------------------------

FORBIDDEN_ENV_PREFIXES = (
    "SUPABASE_",
    "DATABASE_",
    "POSTGRES_",
    "JWT_",
    "OPENAI_",
    "AWS_",
    "GCP_",
    "AZURE_",
)

FORBIDDEN_ENV_KEYS = {
    "PATH",          # avoid letting user influence executable resolution
    "PYTHONPATH",    # avoid module injection
    "PYTHONHOME",
    "VIRTUAL_ENV",
    "PIP_INDEX_URL",
    "PIP_EXTRA_INDEX_URL",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_FILE",
}


def validate_user_env(user_env: dict[str, str]) -> dict[str, str]:
    """
    Strict validation of env vars coming from the request.
    - Rejects secrets/infra-ish prefixes
    - Rejects keys that can influence runtime/module resolution
    - Requires string keys/values
    - Returns a sanitized copy
    """
    if not user_env:
        return {}

    cleaned: dict[str, str] = {}

    for k, v in user_env.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ValueError("All env keys and values must be strings")

        key = k.strip()
        if not key:
            raise ValueError("Env var key cannot be empty")

        # Basic safe identifier check (matches typical env var naming)
        if not key.replace("_", "").isalnum():
            raise ValueError(f"Invalid env var key: {key}")

        if key in FORBIDDEN_ENV_KEYS:
            raise ValueError(f"Forbidden env var key: {key}")

        for prefix in FORBIDDEN_ENV_PREFIXES:
            if key.startswith(prefix):
                raise ValueError(f"Forbidden env var prefix for key: {key}")

        cleaned[key] = v

    return cleaned


def build_subprocess_env(user_env: dict[str, str]) -> dict[str, str]:
    # IMPORTANT: do NOT inherit os.environ
    return {
        **SAFE_BASE_ENV,
        **user_env,  # validated
    }


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventSink:
    """
    Replace this later with a DB writer (or streaming writer).
    """

    def emit(self, event: ExecutionEvent) -> None:
        print(event.model_dump_json())


class PythonShim:
    def __init__(
        self,
        *,
        timeout_s: int = 15,
        allow_imports: Optional[list[str]] = None,
        sink: Optional[EventSink] = None,
    ):
        self.timeout_s = timeout_s
        self.allow_imports = allow_imports or []
        self.sink = sink or EventSink()
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _emit(self, event: ExecutionEvent) -> None:
        self.sink.emit(event)

    async def run(
        self,
        *,
        execution_id: UUID,
        action_source: str,
        entry: str = "action.py",
        event_source: str,
        env: Dict[str, str] | None = None,
    ) -> list[ExecutionEvent]:
        """
        Runs the user action in a subprocess.
        Returns the list of emitted events (in case you want to store them).
        """
        emitted: list[ExecutionEvent] = []

        def capture(event: ExecutionEvent) -> None:
            emitted.append(event)
            self._emit(event)

        start = time.perf_counter()

        # Validate env early, fail before subprocess if unsafe
        try:
            safe_user_env = validate_user_env(env or {})
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            capture(
                ExecutionFailed(
                    execution_id=execution_id,
                    ts=_iso_now(),
                    seq=self._next_seq(),
                    type="execution.failed",
                    error_type="EnvValidationError",
                    message=str(e),
                    exit_code=None,
                    duration_ms=duration_ms,
                    meta={},
                )
            )
            return emitted

        # Temp workspace for isolated execution
        with tempfile.TemporaryDirectory(prefix="hsemulate_py_") as td:
            workdir = Path(td)

            action_path = workdir / entry
            event_path = workdir / "event.json"
            result_path = workdir / "__result.json"
            error_path = workdir / "__error.json"
            runner_path = workdir / "__runner.py"

            action_path.write_text(action_source, encoding="utf-8")
            event_path.write_text(event_source, encoding="utf-8")

            runner_path.write_text(
                _runner_source(
                    entry_filename=entry,
                    allow_imports=self.allow_imports,
                ),
                encoding="utf-8",
            )

            capture(
                ExecutionStarted(
                    execution_id=execution_id,
                    ts=_iso_now(),
                    seq=self._next_seq(),
                    type="execution.started",
                    meta={
                        "entry": entry,
                        "timeout_s": self.timeout_s,
                        "allow_imports": self.allow_imports,
                        "python": sys.version,
                    },
                )
            )

            # Add internal shim variables to the isolated env
            safe_user_env["HSEMULATE_EVENT_PATH"] = str(event_path)
            safe_user_env["HSEMULATE_RESULT_PATH"] = str(result_path)
            safe_user_env["HSEMULATE_ERROR_PATH"] = str(error_path)
            safe_user_env["HSEMULATE_ENTRY"] = entry

            # Use -u for unbuffered output, -I for isolated mode (no user site, ignores env usercustomize)
            python_exe = sys.executable

            proc = await asyncio.create_subprocess_exec(
                python_exe,
                "-I",
                "-u",
                str(runner_path),
                cwd=str(workdir),
                env=build_subprocess_env(safe_user_env),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def read_stream(stream, is_stdout: bool):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").rstrip("\n")
                    if is_stdout:
                        capture(
                            StdoutEmitted(
                                execution_id=execution_id,
                                ts=_iso_now(),
                                seq=self._next_seq(),
                                type="stdout",
                                line=text,
                            )
                        )
                    else:
                        capture(
                            StderrEmitted(
                                execution_id=execution_id,
                                ts=_iso_now(),
                                seq=self._next_seq(),
                                type="stderr",
                                line=text,
                            )
                        )

            stdout_task = asyncio.create_task(read_stream(proc.stdout, True))
            stderr_task = asyncio.create_task(read_stream(proc.stderr, False))

            timed_out = False
            try:
                await asyncio.wait_for(proc.wait(), timeout=self.timeout_s)
            except asyncio.TimeoutError:
                timed_out = True
                proc.kill()
                await proc.wait()
            finally:
                await asyncio.gather(stdout_task, stderr_task)

            duration_ms = int((time.perf_counter() - start) * 1000)

            if timed_out:
                capture(
                    ExecutionTimedOut(
                        execution_id=execution_id,
                        ts=_iso_now(),
                        seq=self._next_seq(),
                        type="execution.timed_out",
                        timeout_s=self.timeout_s,
                        duration_ms=duration_ms,
                        meta={},
                    )
                )
                return emitted

            exit_code = proc.returncode or 0

            # Read structured result or structured error produced by runner.
            if result_path.exists():
                try:
                    result_obj = json.loads(
                        result_path.read_text(encoding="utf-8"))
                    capture(
                        ReturnValue(
                            execution_id=execution_id,
                            ts=_iso_now(),
                            seq=self._next_seq(),
                            type="execution.return",
                            value=result_obj,
                        )
                    )
                    capture(
                        ExecutionCompleted(
                            execution_id=execution_id,
                            ts=_iso_now(),
                            seq=self._next_seq(),
                            type="execution.completed",
                            exit_code=exit_code,
                            duration_ms=duration_ms,
                            meta={},
                        )
                    )
                    return emitted
                except Exception as e:
                    # If runner wrote result but we cannot parse, fail
                    capture(
                        ExecutionFailed(
                            execution_id=execution_id,
                            ts=_iso_now(),
                            seq=self._next_seq(),
                            type="execution.failed",
                            error_type="ResultParseError",
                            message=str(e),
                            exit_code=exit_code,
                            duration_ms=duration_ms,
                            meta={},
                        )
                    )
                    return emitted

            # If no result, check error file
            if error_path.exists():
                try:
                    err = json.loads(error_path.read_text(encoding="utf-8"))
                    capture(
                        ExecutionFailed(
                            execution_id=execution_id,
                            ts=_iso_now(),
                            seq=self._next_seq(),
                            type="execution.failed",
                            error_type=err.get("error_type", "ExecutionError"),
                            message=err.get("message", "Execution failed"),
                            exit_code=exit_code,
                            duration_ms=duration_ms,
                            meta=err.get("meta", {}) or {},
                        )
                    )
                    return emitted
                except Exception as e:
                    capture(
                        ExecutionFailed(
                            execution_id=execution_id,
                            ts=_iso_now(),
                            seq=self._next_seq(),
                            type="execution.failed",
                            error_type="ErrorParseError",
                            message=str(e),
                            exit_code=exit_code,
                            duration_ms=duration_ms,
                            meta={},
                        )
                    )
                    return emitted

            # Fallback: nonzero exit with no structured error
            if exit_code != 0:
                capture(
                    ExecutionFailed(
                        execution_id=execution_id,
                        ts=_iso_now(),
                        seq=self._next_seq(),
                        type="execution.failed",
                        error_type="ProcessExit",
                        message="Python process exited non-zero with no structured error",
                        exit_code=exit_code,
                        duration_ms=duration_ms,
                        meta={},
                    )
                )
                return emitted

            # Edge case: exit 0 but no result written
            capture(
                ExecutionFailed(
                    execution_id=execution_id,
                    ts=_iso_now(),
                    seq=self._next_seq(),
                    type="execution.failed",
                    error_type="MissingResult",
                    message="Execution finished but no result was produced",
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    meta={},
                )
            )
            return emitted


def _runner_source(*, entry_filename: str, allow_imports: list[str]) -> str:
    allow_json = json.dumps(allow_imports)
    return f"""\
import builtins
import importlib.util
import json
import os
import sys
import traceback

ENTRY = os.environ.get("HSEMULATE_ENTRY", {entry_filename!r})
EVENT_PATH = os.environ.get("HSEMULATE_EVENT_PATH")
RESULT_PATH = os.environ.get("HSEMULATE_RESULT_PATH")
ERROR_PATH = os.environ.get("HSEMULATE_ERROR_PATH")

ALLOW_EXTRA = set({allow_json})

# Python 3.10+ provides stdlib list
STDLIB = set(getattr(sys, "stdlib_module_names", ()))

def _write_error(error_type: str, message: str, meta=None):
    if not ERROR_PATH:
        return
    payload = {{
        "error_type": error_type,
        "message": message,
        "meta": meta or {{}},
    }}
    with open(ERROR_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f)

def _write_result(obj):
    if not RESULT_PATH:
        return
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f)

# Import restriction: allow stdlib + explicitly allowed top-level modules.
_real_import = builtins.__import__

def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    top = name.split(".", 1)[0]
    if top in STDLIB or top in ALLOW_EXTRA:
        return _real_import(name, globals, locals, fromlist, level)
    raise ImportError(f"Import not allowed: {{name}}")

builtins.__import__ = _restricted_import

def main():
    if not EVENT_PATH:
        _write_error("MissingEventPath", "HSEMULATE_EVENT_PATH not set")
        sys.exit(2)

    try:
        with open(EVENT_PATH, "r", encoding="utf-8") as f:
            event = json.load(f)
    except Exception as e:
        _write_error("EventParseError", str(e))
        sys.exit(2)

    # Load user module from ENTRY
    try:
        spec = importlib.util.spec_from_file_location("user_action", ENTRY)
        if spec is None or spec.loader is None:
            _write_error("LoadError", f"Could not load entry: {{ENTRY}}")
            sys.exit(2)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        _write_error("UserCodeLoadError", traceback.format_exc())
        sys.exit(1)

    if not hasattr(mod, "main") or not callable(getattr(mod, "main")):
        _write_error("MissingMain", "Entry module must define a callable main(event)")
        sys.exit(1)

    # Execute main(event)
    try:
        ret = mod.main(event)
    except Exception:
        _write_error("UserCodeRuntimeError", traceback.format_exc())
        sys.exit(1)

    # Enforce JSON-serializable return
    try:
        json.dumps(ret)
    except Exception as e:
        _write_error("NonSerializableReturn", f"Return value must be JSON-serializable: {{e}}")
        sys.exit(1)

    # Write result as JSON
    _write_result(ret)
    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        _write_error("RunnerError", traceback.format_exc())
        sys.exit(1)
"""
