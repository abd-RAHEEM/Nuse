from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from hub.modules.jobs.schemas import ApiModel

Provider = Literal["notion", "google_calendar", "gmail"]


class IntegrationSummary(ApiModel):
    id: UUID
    provider: Provider
    status: str
    account_label: str | None
    config: dict = Field(default_factory=dict)
    scopes: list = Field(default_factory=list)
    last_used_at: datetime | None
    last_error: str | None


class IntegrationList(ApiModel):
    items: list[IntegrationSummary]


class NotionConnectRequest(ApiModel):
    token: str | None = Field(default=None, min_length=10, max_length=500)


class OAuthStartResponse(ApiModel):
    auth_url: str


class GmailSyncRunResponse(ApiModel):
    id: UUID
    status: Literal["running", "completed", "failed"]
    mode: Literal["initial", "incremental"]
    messages_scanned: int
    jobs_matched: int
    jobs_updated: int
    review_queued: int
    unmatched_discarded: int
    last_error: str | None
    created_at: datetime
    finished_at: datetime | None


class GmailReviewItem(ApiModel):
    message_id: str
    job_id: UUID
    company: str
    title: str
    sender: str | None
    subject: str
    received_at: datetime
    suggested_status: str | None


class GmailReviewList(ApiModel):
    items: list[GmailReviewItem]


class GmailReviewRequest(ApiModel):
    status: Literal["applied", "assessment", "interview", "offer", "rejected", "ignore"]
class DatabaseItem(ApiModel):
    id: str
    title: str


class DatabaseList(ApiModel):
    items: list[DatabaseItem]


class NotionConfigRequest(ApiModel):
    data_source_id: str = Field(min_length=1, max_length=100)


class NotionExportRequest(ApiModel):
    resource_ids: list[UUID] = Field(min_length=1, max_length=50)


class NotionExportResult(ApiModel):
    resource_id: UUID
    status: Literal["created", "updated", "failed"]
    notion_url: str | None = None
    error: str | None = None


class NotionExportResponse(ApiModel):
    results: list[NotionExportResult]


class CalendarItem(ApiModel):
    id: str
    name: str
    primary: bool = False


class CalendarList(ApiModel):
    items: list[CalendarItem]


class CalendarConfigRequest(ApiModel):
    calendar_id: str = Field(min_length=1, max_length=255)


class CalendarReminder(ApiModel):
    method: Literal["popup"] = "popup"
    minutes: int = Field(ge=0, le=40320)


class CalendarEventRequest(ApiModel):
    job_id: UUID | None = None
    job_event_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=1024)
    description: str | None = Field(default=None, max_length=8192)
    location: str | None = Field(default=None, max_length=1024)
    starts_at: datetime
    ends_at: datetime | None = None
    all_day: bool = False
    time_zone: str = Field(default="UTC", min_length=1, max_length=100)
    reminders: list[CalendarReminder] = Field(default_factory=list, max_length=5)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Calendar event times must include a timezone offset")
        return value

    @field_validator("time_zone")
    @classmethod
    def require_valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Use a valid IANA timezone") from error
        return value

    @model_validator(mode="after")
    def validate_event_links_and_times(self) -> "CalendarEventRequest":
        if self.job_event_id is not None and self.job_id is None:
            raise ValueError("A timeline event must belong to a job")
        if self.job_id is None and not self.title:
            raise ValueError("A title is required for a standalone calendar event")
        if self.ends_at is not None:
            if self.all_day and self.ends_at.date() < self.starts_at.date():
                raise ValueError("The end date must not be before the start date")
            if not self.all_day and self.ends_at <= self.starts_at:
                raise ValueError("The end time must be after the start time")
        return self


class CalendarEventResponse(ApiModel):
    calendar_event_id: str
    html_link: str | None = None
