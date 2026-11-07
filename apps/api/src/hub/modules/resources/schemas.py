from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from hub.modules.jobs.schemas import ApiModel

ResourceCategory = Literal[
    "ai_tool", "course", "certification", "research", "article", "developer_resource", "other"
]


class ResourceSummaryResponse(ApiModel):
    id: UUID
    title: str
    category: ResourceCategory
    source_url: str | None
    source_platform: str | None
    description: str | None
    tags: list[dict[str, str]] = Field(default_factory=list)
    is_favorite: bool
    is_saved_for_later: bool
    collection_ids: list[UUID] = Field(default_factory=list)
    verification_status: str
    created_at: datetime


class ResourcePageResponse(ApiModel):
    items: list["ResourceSummaryResponse"]
    next_cursor: str | None


class ResourceDetailResponse(ResourceSummaryResponse):
    summary: str | None
    notes: str | None
    details: dict | None
    verification_note: str | None
    field_provenance: dict = Field(default_factory=dict)
    updated_at: datetime


class CreateResourceRequest(ApiModel):
    title: str = Field(min_length=1, max_length=200)
    category: ResourceCategory
    source_url: str | None = None
    source_platform: str | None = None
    description: str | None = None
    summary: str | None = None
    notes: str | None = None
    details: dict | None = None
    is_favorite: bool = False
    is_saved_for_later: bool = False
    extraction_id: UUID | None = None
    field_provenance: dict = Field(default_factory=dict)


class UpdateResourceRequest(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: ResourceCategory | None = None
    description: str | None = None
    summary: str | None = None
    notes: str | None = None
    is_favorite: bool | None = None
    is_saved_for_later: bool | None = None
    verification_status: str | None = None
    verification_note: str | None = None


class TagResponse(ApiModel):
    id: UUID
    name: str
    job_count: int = 0
    resource_count: int = 0


class TagListResponse(ApiModel):
    items: list[TagResponse]


class RenameTagRequest(ApiModel):
    name: str = Field(min_length=1, max_length=80)


class CollectionResponse(ApiModel):
    id: UUID
    name: str
    description: str | None
    resource_count: int = 0


class CollectionListResponse(ApiModel):
    items: list[CollectionResponse]


class CreateCollectionRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None


class UpdateCollectionRequest(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
