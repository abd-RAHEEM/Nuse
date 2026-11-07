from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from hub.modules.jobs.schemas import ApiModel

Provider = Literal["notion", "google_calendar"]


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
    token: str = Field(min_length=10, max_length=500)


class OAuthStartResponse(ApiModel):
    auth_url: str


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


class CalendarEventRequest(ApiModel):
    job_id: UUID
    job_event_id: UUID | None = None
    title: str | None = None
    starts_at: datetime
    ends_at: datetime | None = None
    all_day: bool = False
    time_zone: str = "UTC"


class CalendarEventResponse(ApiModel):
    calendar_event_id: str
    html_link: str | None = None
