import csv
import json
from datetime import date, datetime
from io import StringIO
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select

from hub.deps import CurrentUser, DbSession
from hub.models import (
    Application,
    Collection,
    CollectionResource,
    Job,
    JobEvent,
    JobTag,
    Resource,
    ResourceDetail,
    ResourceTag,
    Tag,
)

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])
JOB_FIELDS = [
    "id",
    "company",
    "title",
    "status",
    "appliedOn",
    "nextFollowUpOn",
    "location",
    "employmentType",
    "workMode",
    "sourceUrl",
    "description",
    "requirements",
    "notes",
    "deadline",
    "archived",
    "tags",
    "application",
    "timeline",
    "createdAt",
    "updatedAt",
]
RESOURCE_FIELDS = [
    "id",
    "title",
    "category",
    "sourceUrl",
    "sourcePlatform",
    "description",
    "summary",
    "notes",
    "favorite",
    "savedForLater",
    "verificationStatus",
    "verificationNote",
    "tags",
    "collections",
    "details",
    "createdAt",
    "updatedAt",
]


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _download(
    records: list[dict],
    name: str,
    format: Literal["csv", "json"],
    fields: list[str],
) -> Response:
    if format == "json":
        return Response(
            content=json.dumps(records, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="nuse-{name}.json"'},
        )
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow(
            {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else value
                for key, value in record.items()
            }
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="nuse-{name}.csv"'},
    )


@router.get("/jobs")
async def export_jobs(
    user: CurrentUser,
    db: DbSession,
    format: Literal["csv", "json"] = Query(default="csv"),
    include_archived: bool = Query(default=False, alias="includeArchived"),
) -> Response:
    query = select(Job).where(Job.user_id == user.id).order_by(Job.created_at.asc())
    if not include_archived:
        query = query.where(Job.archived_at.is_(None))
    jobs = list((await db.execute(query)).scalars())
    records: list[dict] = []
    for job in jobs:
        application = await db.scalar(
            select(Application).where(
                Application.job_id == job.id,
                Application.user_id == user.id,
            )
        )
        events = list(
            (
                await db.execute(
                    select(JobEvent)
                    .where(JobEvent.user_id == user.id, JobEvent.job_id == job.id)
                    .order_by(JobEvent.occurred_at.asc())
                )
            ).scalars()
        )
        tags = list(
            (
                await db.execute(
                    select(Tag.name)
                    .join(JobTag, JobTag.tag_id == Tag.id)
                    .where(JobTag.job_id == job.id, Tag.user_id == user.id)
                )
            ).scalars()
        )
        records.append(
            {
                "id": str(job.id),
                "company": job.company,
                "title": job.title,
                "status": application.status if application else "saved",
                "appliedOn": _iso(application.applied_on if application else None),
                "nextFollowUpOn": _iso(
                    application.next_follow_up_on if application else None
                ),
                "location": job.location,
                "employmentType": job.employment_type,
                "workMode": job.work_mode,
                "sourceUrl": job.source_url,
                "description": job.description,
                "requirements": job.requirements,
                "notes": job.notes,
                "deadline": _iso(job.deadline),
                "archived": job.archived_at is not None,
                "tags": tags,
                "application": (
                    {
                        "id": str(application.id),
                        "status": application.status,
                        "appliedOn": _iso(application.applied_on),
                        "nextFollowUpOn": _iso(application.next_follow_up_on),
                        "notes": application.notes,
                    }
                    if application
                    else None
                ),
                "timeline": [
                    {
                        "id": str(event.id),
                        "type": event.type,
                        "title": event.title,
                        "notes": event.notes,
                        "occurredAt": _iso(event.occurred_at),
                        "scheduledFor": _iso(event.scheduled_for),
                        "allDay": event.all_day,
                    }
                    for event in events
                ],
                "createdAt": _iso(job.created_at),
                "updatedAt": _iso(job.updated_at),
            }
        )
    return _download(records, "jobs", format, JOB_FIELDS)


@router.get("/resources")
async def export_resources(
    user: CurrentUser,
    db: DbSession,
    format: Literal["csv", "json"] = Query(default="csv"),
) -> Response:
    resources = list(
        (
            await db.execute(
                select(Resource)
                .where(Resource.user_id == user.id)
                .order_by(Resource.created_at.asc())
            )
        ).scalars()
    )
    records: list[dict] = []
    for resource in resources:
        tags = list(
            (
                await db.execute(
                    select(Tag.name)
                    .join(ResourceTag, ResourceTag.tag_id == Tag.id)
                    .where(
                        ResourceTag.resource_id == resource.id,
                        Tag.user_id == user.id,
                    )
                )
            ).scalars()
        )
        collections = list(
            (
                await db.execute(
                    select(Collection.name)
                    .join(
                        CollectionResource,
                        CollectionResource.collection_id == Collection.id,
                    )
                    .where(
                        CollectionResource.resource_id == resource.id,
                        Collection.user_id == user.id,
                    )
                )
            ).scalars()
        )
        details = await db.scalar(
            select(ResourceDetail).where(ResourceDetail.resource_id == resource.id)
        )
        records.append(
            {
                "id": str(resource.id),
                "title": resource.title,
                "category": resource.category,
                "sourceUrl": resource.source_url,
                "sourcePlatform": resource.source_platform,
                "description": resource.description,
                "summary": resource.summary,
                "notes": resource.notes,
                "favorite": resource.is_favorite,
                "savedForLater": resource.is_saved_for_later,
                "verificationStatus": resource.verification_status,
                "verificationNote": resource.verification_note,
                "tags": tags,
                "collections": collections,
                "details": details.data if details else None,
                "createdAt": _iso(resource.created_at),
                "updatedAt": _iso(resource.updated_at),
            }
        )
    return _download(records, "resources", format, RESOURCE_FIELDS)
