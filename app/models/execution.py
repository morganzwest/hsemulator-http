from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class ActionLanguage(str, Enum):
    python = "python"
    js = "js"              # user request format
    javascript = "javascript"


class ActionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: ActionLanguage
    entry: str = Field(..., min_length=1, description="action.py or action.js")
    source: str = Field(..., min_length=1, description="Raw code as a string")


class FixtureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1,
                        description="Fixture file content as a string")


class ExecuteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ActionConfig
    fixtures: List[FixtureConfig] = Field(default_factory=list)

    # Env values are strings in the request (often IDs of secrets in DB)
    env: Dict[str, str] = Field(default_factory=dict)

    repeat: int = Field(1, ge=1, description="Must be a number >= 1")


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["execute"]
    execution_id: UUID = Field(
        ...,
        description="Execution ID (UUID, matches action_executions.execution_id)",
    )
    config: ExecuteConfig


class ExecuteAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    execution_id: UUID
    status: str
