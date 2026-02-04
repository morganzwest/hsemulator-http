from pydantic import BaseModel, Field, model_validator
from uuid import UUID
from typing import Optional, Literal


SecretScope = Literal["portal", "action", "cicd"]


class CreateSecretRequest(BaseModel):
    """
    Request to create a new encrypted secret.

    The secret value is provided in plaintext and encrypted at rest by the platform.
    Secrets can be scoped to a portal, a specific action, or CI/CD usage.
    """

    scope: SecretScope = Field(
        ...,
        description=(
            "Scope of the secret. Determines where the secret can be used.\n\n"
            "- `portal`: Available to all actions within a portal\n"
            "- `action`: Available only to a specific action\n"
            "- `cicd`: Available for CI/CD or automation contexts"
        ),
        examples=["portal"],
    )

    portal_id: Optional[UUID] = Field(
        None,
        description=(
            "Portal ID the secret belongs to. "
            "Required for `portal`, `action`, and `cicd` scopes."
        ),
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )

    action_id: Optional[UUID] = Field(
        None,
        description=(
            "Action ID the secret is bound to. "
            "Required only when `scope` is `action`."
        ),
        examples=["82caec1c-5c66-4c40-9e6a-7ea7c4bac922"],
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description=(
            "Human-readable name for the secret. "
            "Must be unique within the given scope."
        ),
        examples=["API_KEY"],
    )

    value: str = Field(
        ...,
        min_length=1,
        description=(
            "Plaintext value of the secret at creation time. "
            "This value is encrypted immediately and never returned by the API."
        ),
        examples=["sk_test_123456"],
    )

    created_by: Optional[UUID] = Field(
        None,
        description=(
            "Optional ID of the user creating the secret. "
            "If omitted, defaults to the authenticated user."
        ),
        examples=["9f1c2d45-8c0a-4f5e-9f2a-1d3b6e9c1234"],
    )

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
    """
    Response returned after a secret is successfully created.
    """

    ok: bool = Field(
        ...,
        description="Indicates whether the secret was created successfully.",
        examples=[True],
    )

    secret_id: UUID = Field(
        ...,
        description="Unique ID of the newly created secret.",
        examples=["82caec1c-5c66-4c40-9e6a-7ea7c4bac922"],
    )


class UpdateSecretRequest(BaseModel):
    """
    Request to update the value of an existing secret.

    The provided value is plaintext and will be re-encrypted at rest.
    """
    value: str = Field(
        ...,
        min_length=1,
        description="New plaintext value for the secret.",
        examples=["sk_live_987654"],
    )


class UpdateSecretResponse(BaseModel):
    """
    Response returned after a secret is successfully updated.
    """
    ok: bool = Field(
        ...,
        description="Indicates whether the secret was updated successfully.",
        examples=[True],
    )
    secret_id: UUID = Field(
        ...,
        description="ID of the updated secret.",
        examples=["82caec1c-5c66-4c40-9e6a-7ea7c4bac922"],
    )

class DeleteSecretResponse(BaseModel):
    """
    Response returned after a secret is successfully deleted.
    """
    ok: bool = Field(
        ...,
        description="Indicates whether a secret ws deleted successfully",
        examples=[True],
    )
    secret_id: UUID = Field(
        ...,
        description="ID of the deleted secret.",
        examples=["82caec1c-5c66-4c40-9e6a-7ea7c4bac922"]
    )