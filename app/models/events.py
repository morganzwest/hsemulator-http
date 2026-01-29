from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Union
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ExecutionEventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: UUID
    ts: datetime = Field(..., description="UTC timestamp")
    seq: int = Field(..., ge=1,
                     description="Monotonic sequence number for ordering")


class ExecutionStarted(ExecutionEventBase):
    type: Literal["execution.started"]
    meta: Dict[str, Any] = Field(default_factory=dict)


class StdoutEmitted(ExecutionEventBase):
    type: Literal["stdout"]
    line: str


class StderrEmitted(ExecutionEventBase):
    type: Literal["stderr"]
    line: str


class ReturnValue(ExecutionEventBase):
    type: Literal["execution.return"]
    value: Any


class ExecutionCompleted(ExecutionEventBase):
    type: Literal["execution.completed"]
    ok: bool = True
    exit_code: int
    duration_ms: int
    meta: Dict[str, Any] = Field(default_factory=dict)


class ExecutionFailed(ExecutionEventBase):
    type: Literal["execution.failed"]
    ok: bool = False
    error_type: str
    message: str
    exit_code: Optional[int] = None
    duration_ms: Optional[int] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ExecutionTimedOut(ExecutionEventBase):
    type: Literal["execution.timed_out"]
    ok: bool = False
    timeout_s: int
    duration_ms: int
    meta: Dict[str, Any] = Field(default_factory=dict)


ExecutionEvent = Union[
    ExecutionStarted,
    StdoutEmitted,
    StderrEmitted,
    ReturnValue,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionTimedOut,
]
