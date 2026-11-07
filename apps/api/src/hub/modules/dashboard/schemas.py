from datetime import datetime
from uuid import UUID

from pydantic import Field

from hub.modules.jobs.schemas import ApiModel


class DashboardUser(ApiModel):
    display_name: str | None
    username: str


class DashboardCounts(ApiModel):
    applications_tracked: int
    interviews_active: int
    resources_total: int


class DashboardJob(ApiModel):
    id: UUID
    company: str
    title: str


class DashboardUpcoming(ApiModel):
    kind: str
    at: str
    all_day: bool
    overdue: bool
    job: DashboardJob
    event_id: UUID | None


class DashboardActivity(ApiModel):
    id: UUID
    job_id: UUID
    type: str
    title: str
    notes: str | None
    occurred_at: datetime
    scheduled_for: datetime | None
    all_day: bool
    system: bool
    calendar_linked: bool
    created_at: datetime
    job: DashboardJob


class DashboardResource(ApiModel):
    id: UUID
    title: str
    category: str
    source_url: str | None
    source_platform: str | None
    description: str | None
    tags: list[dict[str, str]] = Field(default_factory=list)
    is_favorite: bool
    is_saved_for_later: bool
    collection_ids: list[UUID] = Field(default_factory=list)
    verification_status: str
    created_at: datetime


class DashboardResponse(ApiModel):
    user: DashboardUser
    counts: DashboardCounts
    upcoming: list[DashboardUpcoming]
    recent_activity: list[DashboardActivity]
    recent_resources: list[DashboardResource]
