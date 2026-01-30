from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class SecretEnvRef(BaseModel):
    """
    Reference to a stored secret that will be resolved and injected
    into the execution environment at runtime.
    """
    model_config = ConfigDict(extra="forbid")

    type: Literal["secret"] = Field(
        "secret",
        description="Discriminator indicating this env value is a secret reference.",
        examples=["secret"],
    )
    secret_id: UUID = Field(
        ...,
        description="UUID of the secret to decrypt and inject at runtime.",
        examples=["82caec1c-5c66-4c40-9e6a-7ea7c4bac922"],
    )


EnvValue = Union[str, SecretEnvRef]


class ActionLanguage(str, Enum):
    """
    Language the action source code is written in.
    """
    python = "python"
    js = "js"              # user request format
    javascript = "javascript"


class ActionConfig(BaseModel):
    """
    Definition of the executable action.
    """
    model_config = ConfigDict(extra="forbid")

    language: ActionLanguage = Field(
        ...,
        description="Programming language used by the action.",
        examples=["python"],
    )
    entry: str = Field(
        ...,
        min_length=1,
        description="Entry filename for the action (e.g. action.py or action.js).",
        examples=["action.py"],
    )
    source: str = Field(
        ...,
        min_length=1,
        description="Raw source code of the action as a string.",
        examples=[
            "def main(event):\n    print('hello world')\n    return {'ok': True}"
        ],
    )


class FixtureConfig(BaseModel):
    """
    Static fixture file made available to the execution runtime.
    """
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        description="Filename of the fixture (e.g. event.json).",
        examples=["event.json"],
    )
    source: str = Field(
        ...,
        min_length=1,
        description="Fixture file contents as a string.",
        examples=['{ "inputFields": { "name": "Morgan" } }'],
    )


class ExecuteConfig(BaseModel):
    """
    Configuration describing how an execution should run.
    """
    model_config = ConfigDict(extra="forbid")

    action: ActionConfig

    fixtures: List[FixtureConfig] = Field(
        default_factory=list,
        description="Optional list of fixture files available during execution.",
    )

    env: Dict[str, EnvValue] = Field(
        default_factory=dict,
        description=(
            "Environment variables injected into the execution runtime. "
            "Values may be plain strings or secret references. "
            "Secrets are decrypted by the platform and never exposed in logs or responses."
        ),
        examples=[
            {
                "MODE": "test",
                "API_KEY": {
                    "type": "secret",
                    "secret_id": "82caec1c-5c66-4c40-9e6a-7ea7c4bac922",
                },
            }
        ],
    )

    repeat: int = Field(
        1,
        ge=1,
        description=(
            "Number of times to execute the action. "
            "Primarily intended for testing or benchmarking."
        ),
        examples=[1],
    )


class ExecuteRequest(BaseModel):
    """
    Request to execute an action.
    """
    model_config = ConfigDict(extra="forbid")

    mode: Literal["execute"] = Field(
        ...,
        description="Execution mode. Currently only 'execute' is supported.",
        examples=["execute"],
    )

    execution_id: UUID = Field(
        ...,
        description="Execution ID (must match action_executions.execution_id).",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )

    config: ExecuteConfig = Field(
        ...,
        description="Execution configuration.",
    )


class ExecuteAcceptedResponse(BaseModel):
    """
    Response returned when an execution is accepted.
    """
    model_config = ConfigDict(extra="forbid")

    ok: bool = Field(
        ...,
        description="Indicates whether the execution request was accepted.",
        examples=[True],
    )
    execution_id: UUID = Field(
        ...,
        description="Execution ID associated with the request.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    status: str = Field(
        ...,
        description="Initial execution status.",
        examples=["queued"],
    )
