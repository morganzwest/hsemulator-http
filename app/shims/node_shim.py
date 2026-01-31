from __future__ import annotations
import os
import asyncio
import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List
from uuid import UUID

from app.models.events import (
    ExecutionCompleted,
    ExecutionEvent,
    ExecutionFailed,
    ExecutionStarted,
    ExecutionTimedOut,
    ReturnValue,
    StdoutEmitted,
    StderrEmitted,
)
from app.shims.python_shim import (
    validate_user_env,
    build_subprocess_env,
    Redactor,
    redact_obj,
    PlatformExecutionError,
    PLATFORM_ERROR_MESSAGE,
    PLATFORM_ERROR_TYPE,
)


# Node runner (ESM). Writes __result.json or __error.json deterministically.
# Notes:
# - Supports both ESM: `export async function main(event) { ... }`
# - And CJS default: `module.exports.main = async (event) => { ... }` if imported via createRequire.
# - Ensures RESULT/ERROR files are always attempted before exit.
# - Never throws uncaught errors without writing ERROR file first.
_NODE_RUNNER_SOURCE = r"""
import fs from "fs";
import path from "path";
import { pathToFileURL } from "url";
import { createRequire } from "module";
import Module from "module";

const ALLOWED_PACKAGES = new Set([
  "@hubspot/api-client",
  "async",
  "aws-sdk",
  "axios",
  "lodash",
  "mongoose",
  "mysql",
  "redis",
  "request",
  "bluebird",
  "random-number-csprng",
  "googleapis",
]);

const BUILTINS = new Set(Module.builtinModules);

function isAllowedResolvedPath(resolvedPath, workdir) {
  // Allow entry file itself
  if (resolvedPath.startsWith(workdir)) return true;

  // Allow node_modules/<allowed-package>/...
  const nm = path.sep + "node_modules" + path.sep;
  const idx = resolvedPath.lastIndexOf(nm);
  if (idx === -1) return false;

  const remainder = resolvedPath.slice(idx + nm.length);
  const pkg = remainder.startsWith("@")
    ? remainder.split(path.sep).slice(0, 2).join("/")
    : remainder.split(path.sep)[0];

  return ALLOWED_PACKAGES.has(pkg);
}

const ENTRY = process.env.HSEMULATE_ENTRY || "action.js";
const EVENT_PATH = process.env.HSEMULATE_EVENT_PATH;
const RESULT_PATH = process.env.HSEMULATE_RESULT_PATH;
const ERROR_PATH = process.env.HSEMULATE_ERROR_PATH;

function writeJson(filePath, obj) {
  fs.writeFileSync(filePath, JSON.stringify(obj), { encoding: "utf8" });
}

function writeError(type, message, meta = {}) {
  if (!ERROR_PATH) return;
  writeJson(ERROR_PATH, { error_type: type, message, meta });
}

function writeResult(obj) {
  if (!RESULT_PATH) return;
  writeJson(RESULT_PATH, obj);
}

function safeString(x) {
  try { return String(x); } catch { return "Unknown error"; }
}

async function restrictedLoad(entryPathAbs, workdir) {
  const originalResolve = Module._resolveFilename;

  Module._resolveFilename = function (request, parent, isMain, options) {
    // Allow builtins
    if (BUILTINS.has(request)) {
      return originalResolve.apply(this, arguments);
    }

    const resolved = originalResolve.apply(this, arguments);

    if (!isAllowedResolvedPath(resolved, workdir)) {
      throw new Error(`Import not allowed: ${request}`);
    }

    return resolved;
  };

  try {
    return await import(pathToFileURL(entryPathAbs).href);
  } finally {
    Module._resolveFilename = originalResolve;
  }
}

(async () => {
  try {
    if (!EVENT_PATH) {
      writeError("MissingEventPath", "HSEMULATE_EVENT_PATH not set");
      process.exit(2);
    }
    if (!RESULT_PATH) {
      writeError("MissingResultPath", "HSEMULATE_RESULT_PATH not set");
      process.exit(2);
    }
    if (!ERROR_PATH) {
      // If we cannot write errors, still attempt to fail clearly.
      process.stderr.write("HSEMULATE_ERROR_PATH not set\n");
      process.exit(2);
    }

    let event;
    try {
      event = JSON.parse(fs.readFileSync(EVENT_PATH, "utf8"));
    } catch (e) {
      writeError("EventParseError", e?.message || safeString(e));
      process.exit(2);
    }

    const entryAbs = path.resolve(ENTRY);

    let mod;
    try {
      mod = await restrictedLoad(entryAbs, process.cwd());
    } catch (e) {
      writeError("UserCodeLoadError", e?.stack || safeString(e), e?.meta || {});
      process.exit(1);
    }

    const fn = (mod && typeof mod.main === "function")
      ? mod.main
      : (mod && mod.default && typeof mod.default.main === "function")
        ? mod.default.main
        : null;

    if (typeof fn !== "function") {
      writeError("MissingMain", "Module must export a callable main(event) (ESM export or module.exports)");
      process.exit(1);
    }

    let result;
    try {
      result = await fn(event);
    } catch (e) {
      writeError("UserCodeRuntimeError", e?.stack || safeString(e));
      process.exit(1);
    }

    try {
      JSON.stringify(result);
    } catch (e) {
      writeError("NonSerializableReturn", "Return value must be JSON-serializable: " + (e?.message || safeString(e)));
      process.exit(1);
    }

    try {
      writeResult(result);
    } catch (e) {
      writeError("ResultWriteError", e?.stack || safeString(e));
      process.exit(1);
    }

    process.exit(0);
  } catch (e) {
    try {
      writeError("RunnerError", e?.stack || safeString(e));
    } catch {}
    process.exit(1);
  }
})();
"""


def build_node_subprocess_env(user_env: dict[str, str]) -> dict[str, str]:
    """
    Node.js on Windows requires certain system env vars to exist
    for crypto / OpenSSL initialization.
    """
    base = {}

    # REQUIRED on Windows for Node crypto
    for k in ("SystemRoot", "WINDIR", "COMSPEC"):
        if k in os.environ:
            base[k] = os.environ[k]

    # PATH is required for DLL resolution
    if "PATH" in os.environ:
        base["PATH"] = os.environ["PATH"]

    return {
        **base,
        **user_env,
    }


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NodeShim:
    """
    Drop-in node shim with parity to PythonShim behavior:
    - Emits started/stdout/stderr/return/completed/failed/timed_out
    - Uses the same env validation + redaction logic
    - Does NOT crash the worker for user failures
    - Only raises for platform failures (consistent with PythonShim)
    """

    def __init__(self, *, timeout_s: int = 15, sink):
        self.timeout_s = timeout_s
        self.sink = sink
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _emit(self, ev: ExecutionEvent) -> None:
        self.sink.emit(ev)

    async def run(
        self,
        *,
        execution_id: UUID,
        action_source: str,
        entry: str = "action.js",
        event_source: str,
        env: Dict[str, str] | None = None,
    ) -> List[ExecutionEvent]:
        emitted: List[ExecutionEvent] = []

        def capture(ev: ExecutionEvent) -> None:
            emitted.append(ev)
            self._emit(ev)

        start = time.perf_counter()

        try:
            # 1) Env validation: user error is safe to show (match PythonShim)
            try:
                safe_user_env = validate_user_env(env or {})
                redactor = Redactor(safe_user_env)
            except ValueError as e:
                capture(
                    ExecutionFailed(
                        execution_id=execution_id,
                        ts=_iso_now(),
                        seq=self._next_seq(),
                        type="execution.failed",
                        error_type="EnvValidationError",
                        message=str(e),
                        exit_code=None,
                        duration_ms=int((time.perf_counter() - start) * 1000),
                        meta={},
                    )
                )
                return emitted
            except Exception as e:
                # Unexpected env validation failure -> platform
                raise PlatformExecutionError() from e

            # 2) Temp workspace includes subprocess lifetime
            with tempfile.TemporaryDirectory(prefix="hsemulate_node_") as td:
                workdir = Path(td)

                # Ensure we have a reasonable entry filename for Node.
                # If caller passes "action.py" by accident, we still write it,
                # but node runner will load it and fail with structured error.
                action_path = workdir / entry
                event_path = workdir / "event.json"
                result_path = workdir / "__result.json"
                error_path = workdir / "__error.json"
                runner_path = workdir / "__runner.mjs"

                try:
                    action_path.write_text(action_source, encoding="utf-8")
                    event_path.write_text(event_source, encoding="utf-8")
                    runner_path.write_text(
                        _NODE_RUNNER_SOURCE, encoding="utf-8")
                except Exception as e:
                    raise PlatformExecutionError() from e

                # 3) started event
                capture(
                    ExecutionStarted(
                        execution_id=execution_id,
                        ts=_iso_now(),
                        seq=self._next_seq(),
                        type="execution.started",
                        meta={
                            "entry": entry,
                            "timeout_s": self.timeout_s,
                            "runtime": "node",
                        },
                    )
                )

                # Shim vars (mirror PythonShim)
                safe_user_env["HSEMULATE_EVENT_PATH"] = str(event_path)
                safe_user_env["HSEMULATE_RESULT_PATH"] = str(result_path)
                safe_user_env["HSEMULATE_ERROR_PATH"] = str(error_path)
                safe_user_env["HSEMULATE_ENTRY"] = entry

                node_exe = shutil.which("node")
                if not node_exe:
                    # Platform failure (infra)
                    raise PlatformExecutionError()  # use generic platform message

                # 4) Spawn node subprocess
                try:
                    proc = await asyncio.create_subprocess_exec(
                        node_exe,
                        str(runner_path),
                        cwd=str(workdir),
                        env=build_node_subprocess_env(safe_user_env),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                except Exception as e:
                    raise PlatformExecutionError() from e

                async def read_stream(stream: asyncio.StreamReader, is_stdout: bool) -> None:
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        text = line.decode(
                            "utf-8", errors="replace").rstrip("\n")
                        text = redactor.redact(text)
                        capture(
                            (StdoutEmitted if is_stdout else StderrEmitted)(
                                execution_id=execution_id,
                                ts=_iso_now(),
                                seq=self._next_seq(),
                                type="stdout" if is_stdout else "stderr",
                                line=text,
                            )
                        )

                stdout_task = asyncio.create_task(
                    read_stream(proc.stdout, True))
                stderr_task = asyncio.create_task(
                    read_stream(proc.stderr, False))

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
                exit_code = proc.returncode if proc.returncode is not None else 0

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

                # 5) Parse result/error files (mirror PythonShim)
                if result_path.exists():
                    try:
                        result_obj = json.loads(
                            result_path.read_text(encoding="utf-8"))
                        safe_result = redact_obj(result_obj, redactor)
                    except Exception as e:
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

                    capture(
                        ReturnValue(
                            execution_id=execution_id,
                            ts=_iso_now(),
                            seq=self._next_seq(),
                            type="execution.return",
                            value=safe_result,
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

                if error_path.exists():
                    try:
                        err = json.loads(
                            error_path.read_text(encoding="utf-8"))
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

                    msg = err.get("message", "Execution failed")
                    msg = redactor.redact(msg)

                    capture(
                        ExecutionFailed(
                            execution_id=execution_id,
                            ts=_iso_now(),
                            seq=self._next_seq(),
                            type="execution.failed",
                            error_type=err.get("error_type", "ExecutionError"),
                            message=msg,
                            exit_code=exit_code,
                            duration_ms=duration_ms,
                            meta=err.get("meta", {}) or {},
                        )
                    )
                    return emitted

                # 6) Fallbacks (match PythonShim behavior)
                if exit_code != 0:
                    capture(
                        ExecutionFailed(
                            execution_id=execution_id,
                            ts=_iso_now(),
                            seq=self._next_seq(),
                            type="execution.failed",
                            error_type="ProcessExit",
                            message="Node process exited non-zero with no structured error",
                            exit_code=exit_code,
                            duration_ms=duration_ms,
                            meta={},
                        )
                    )
                    return emitted

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

        except PlatformExecutionError:
            duration_ms = int((time.perf_counter() - start) * 1000)
            capture(
                ExecutionFailed(
                    execution_id=execution_id,
                    ts=_iso_now(),
                    seq=self._next_seq(),
                    type="execution.failed",
                    error_type=PLATFORM_ERROR_TYPE,
                    message=PLATFORM_ERROR_MESSAGE,
                    exit_code=None,
                    duration_ms=duration_ms,
                    meta={},
                )
            )
            raise

        except Exception:
            duration_ms = int((time.perf_counter() - start) * 1000)
            capture(
                ExecutionFailed(
                    execution_id=execution_id,
                    ts=_iso_now(),
                    seq=self._next_seq(),
                    type="execution.failed",
                    error_type=PLATFORM_ERROR_TYPE,
                    message=PLATFORM_ERROR_MESSAGE,
                    exit_code=None,
                    duration_ms=duration_ms,
                    meta={},
                )
            )
            import logging as _logging
            _logging.exception(
                "Unhandled platform error during node execution",
                extra={"execution_id": execution_id},
            )
            raise
