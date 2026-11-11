from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class AuthRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    pin: str = Field(min_length=6, max_length=6)
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        if not value.isdecimal():
            raise ValueError("PIN must contain six digits")
        if len(set(value)) == 1 or value in {"012345", "123456", "654321"}:
            raise ValueError("Choose a less predictable PIN")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    username: str
    display_name: str | None
    created_at: datetime


class AuthResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    user: UserResponse


class ChangePinRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    current_pin: str = Field(min_length=6, max_length=6)
    new_pin: str = Field(min_length=6, max_length=6)

    @field_validator("current_pin", "new_pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        if not value.isdecimal():
            raise ValueError("PIN must contain six digits")
        if len(set(value)) == 1 or value in {"012345", "123456", "654321"}:
            raise ValueError("Choose a less predictable PIN")
        return value
