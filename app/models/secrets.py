from pydantic import BaseModel, Field, model_validator
from uuid import UUID
from typing import Optional, Literal


SecretScope = Literal["portal", "action", "cicd"]


class CreateSecretRequest(BaseModel):
    scope: SecretScope

    portal_id: Optional[UUID] = None
    action_id: Optional[UUID] = None

    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1)

    created_by: Optional[UUID] = None

    @model_validator(mode="after")
    def validate_scope_rules(self):
        if self.scope == "portal":
            if not self.portal_id:
                raise ValueError("portal scope requires portal_id")
            if self.action_id is not None:
                raise ValueError("portal scope must not include action_id")

        elif self.scope == "action":
            if not self.portal_id or not self.action_id:
                raise ValueError(
                    "action scope requires both portal_id and action_id"
                )

        elif self.scope == "cicd":
            if not self.portal_id:
                raise ValueError("cicd scope requires portal_id")
            if self.action_id is not None:
                raise ValueError("cicd scope must not include action_id")

        return self


class CreateSecretResponse(BaseModel):
    ok: bool
    secret_id: UUID
