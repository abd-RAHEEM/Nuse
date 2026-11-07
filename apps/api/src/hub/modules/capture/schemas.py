from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from hub.modules.jobs.schemas import ApiModel


class CreateExtractionRequest(ApiModel):
    type: Literal["job", "resource"]
    url: str | None = Field(default=None, max_length=2048)
    text: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def require_input(self):
        if not self.url and not self.text:
            raise ValueError("Provide a URL or text to capture")
        return self


class ExtractionResponse(ApiModel):
    id: UUID
    type: Literal["job", "resource"]
    status: str
    input: dict
    detected_source: dict
    detected_type: str
    steps: list[dict]
    result: dict | None
    error: dict | None
    duplicate_of: dict | None
    created_at: datetime
    finished_at: datetime | None
