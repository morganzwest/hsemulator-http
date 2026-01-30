# HS Emulator – Python HTTP

## Goal

HS Emulator is a **secure, deterministic runtime** for executing user-provided Python actions in isolation.

It is designed to:

- Safely execute untrusted code
- Capture all execution events in real time
- Prevent access to secrets, the host environment, and the filesystem
- Provide clear separation between **user errors** and **platform errors**
- Mirror production-style execution (timeouts, logs, structured output)

This is intended for **workflow actions, automations, and integrations**, not general-purpose scripting.

---

## What This Is (and Isn’t)

**This is:**

- A controlled execution sandbox
- Deterministic and replayable
- Event-driven (every execution emits a timeline of events)
- Secure by default

**This is not:**

- A general Python REPL
- A VM or container orchestrator
- A dependency installer
- A long-running process host

---

## High-Level Architecture

```
┌──────────────┐
│ API / Worker │
└──────┬───────┘
       │
       ▼
┌─────────────────────┐
│ PythonShim          │
│ (Orchestrator)      │
│                     │
│ - Validates env     │
│ - Creates workspace │
│ - Starts subprocess │
│ - Emits events      │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ Isolated Subprocess │
│ (__runner.py)       │
│                     │
│ - Import guard      │
│ - Executes user     │
│ - Writes result     │
│ - Writes errors     │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ Event Sink          │
│ (DB / Realtime)     │
│                     │
│ - stdout / stderr   │
│ - lifecycle events  │
│ - failures          │
└─────────────────────┘
```

Each execution runs in:

- A **temporary directory**
- A **fresh Python process**
- A **fully controlled environment**

No state is shared between runs.

---

## Core Features

### ✅ Secure Execution

- Runs code in a subprocess (`-I -u`)
- No inherited environment variables
- No filesystem access outside the temp workspace

### ✅ Environment Variable Safety

- Explicit allow-list only
- Deny-listed prefixes (`SUPABASE_`, `AWS_`, `JWT_`, etc.)
- Dangerous keys blocked (`PATH`, `PYTHONPATH`, etc.)

### ✅ Import Allow List

- Only stdlib + explicitly allowed third-party modules
- Transitive imports enforced (e.g. `requests → urllib3`)
- Fails fast on disallowed imports

### ✅ Execution Lifecycle Events

Every run emits structured events, including:

- `ExecutionStarted`
- `Stdout`
- `Stderr`
- `ExecutionCompleted`
- `ExecutionFailed`
- `ExecutionTimedOut`
- `ReturnValue`

### ✅ Real-Time Event Streaming

- Events are persisted as they happen
- Suitable for live UIs and logs
- No buffering or post-processing required

### ✅ Clear Error Classification

Errors are intentionally separated into:

- **User errors** (bad code, runtime exceptions)
- **Validation errors** (env/import issues)
- **Platform errors** (shim or infra failures)

Platform errors never leak internal stack traces to users.

### ✅ Redaction Layer

- Any provided env value is automatically redacted from:
  - stdout
  - stderr
  - return values

- Secrets cannot be leaked accidentally

### ✅ Deterministic Timeouts

- Hard execution timeout
- Process is killed on timeout
- Emits a structured timeout event

---

## Passing Request Example

This request:

- Uses an allowed env var
- Prints safely
- Returns JSON

```json
{
  "mode": "execute",
  "execution_id": "4e4038f3-03dc-49d9-befb-1bf4db3453ae",
  "config": {
    "action": {
      "language": "python",
      "entry": "action.py",
      "source": "import os\n\ndef main(event):\n    value = os.getenv(\"TEST_ENV_VAR\")\n    print(\"TEST_ENV_VAR =\", value)\n\n    return {\n        \"ok\": True,\n        \"env_value\": value\n    }\n"
    },
    "fixtures": [
      {
        "name": "event.json",
        "source": "{ \"inputFields\": {} }"
      }
    ],
    "env": {
      "TEST_ENV_VAR": \"hello-from-env\"
    },
    "repeat": 1
  }
}
```

**Result:**

- Execution completes
- `stdout` emitted
- `ReturnValue` emitted
- No secrets leaked

---

## Failing Request Example (Import Guard)

This request attempts to import a module that is **not allowed**.

```json
{
  "mode": "execute",
  "execution_id": "4e4038f3-03dc-49d9-befb-1bf4db3453ae",
  "config": {
    "action": {
      "language": "python",
      "entry": "action.py",
      "source": "import requests\n\ndef main(event):\n    return {\"ok\": true}\n"
    },
    "fixtures": [
      {
        "name": "event.json",
        "source": "{ \"inputFields\": {} }"
      }
    ],
    "env": {},
    "repeat": 1
  }
}
```

**Result:**

- Execution fails during import
- `ExecutionFailed` emitted
- Error classified as **user code load error**
- No platform stack traces exposed

---

## Design Philosophy

- **Explicit > implicit**
- **Fail fast**
- **No magic**
- **Security first**
- **Everything is observable**

This runtime is intentionally strict.
If something runs here, it will run **predictably and safely** in production.
