from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class JobPageResponse(ApiModel):
    items: list["JobSummaryResponse"]
    next_cursor: str | None


JobStatus = Literal[
    "saved",
    "applied",
    "assessment",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
    "on_hold",
]


class ApplicationResponse(ApiModel):
    id: UUID
    status: JobStatus
    applied_on: date | None
    next_follow_up_on: date | None
    notes: str | None


class JobEventResponse(ApiModel):
    id: UUID
    job_id: UUID
    type: str
    title: str
    notes: str | None
    occurred_at: datetime
    scheduled_for: datetime | None
    all_day: bool
    system: bool = False
    calendar_linked: bool = False
    created_at: datetime


class JobSummaryResponse(ApiModel):
    id: UUID
    company: str
    title: str
    location: str | None
    employment_type: str | None
    work_mode: str | None
    status: JobStatus
    applied_on: date | None
    next_follow_up_on: date | None
    deadline: date | None
    tags: list[dict[str, str]] = Field(default_factory=list)
    source_url: str | None
    archived: bool
    created_at: datetime
    updated_at: datetime


class JobDetailResponse(JobSummaryResponse):
    external_job_id: str | None
    description: str | None
    requirements: str | None
    notes: str | None
    application: ApplicationResponse | None
    timeline: list[JobEventResponse]
    extraction_id: UUID | None = None
    field_provenance: dict = Field(default_factory=dict)


class CreateJobRequest(ApiModel):
    intent: Literal["saved", "applied"]
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    source_url: str | None = None
    location: str | None = Field(default=None, max_length=200)
    employment_type: str | None = None
    work_mode: str | None = None
    description: str | None = Field(default=None, max_length=50000)
    requirements: str | None = None
    deadline: date | None = None
    notes: str | None = None
    applied_on: date | None = None
    next_follow_up_on: date | None = None
    extraction_id: UUID | None = None
    field_provenance: dict = Field(default_factory=dict)


class UpdateJobRequest(ApiModel):
    company: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    status: JobStatus | None = None
    applied_on: date | None = None
    next_follow_up_on: date | None = None
    notes: str | None = None
    archived: bool | None = None


class CreateEventRequest(ApiModel):
    type: Literal["assessment", "interview", "follow_up", "note"]
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = None
    occurred_at: datetime | None = None
    scheduled_for: datetime | None = None
    all_day: bool = False


class UpdateEventRequest(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = None
    occurred_at: datetime | None = None
    scheduled_for: datetime | None = None
    all_day: bool | None = None
