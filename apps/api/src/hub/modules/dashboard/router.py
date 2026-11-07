from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import func, select

from hub.deps import CurrentUser, DbSession
from hub.models import Application, Job, JobEvent, Resource
from hub.modules.dashboard.schemas import DashboardResponse

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def dashboard(user: CurrentUser, db: DbSession) -> DashboardResponse:
    applications = await db.scalar(
        select(func.count(Application.id)).where(Application.user_id == user.id)
    )
    interviews = await db.scalar(
        select(func.count(Application.id)).where(
            Application.user_id == user.id,
            Application.status == "interview",
        )
    )
    resources = await db.scalar(
        select(func.count(Resource.id)).where(Resource.user_id == user.id)
    )
    recent_resources = (
        await db.execute(
            select(Resource)
            .where(Resource.user_id == user.id)
            .order_by(Resource.created_at.desc())
            .limit(5)
        )
    ).scalars()
    upcoming = (
        await db.execute(
            select(JobEvent, Job)
            .join(Job, Job.id == JobEvent.job_id)
            .where(
                JobEvent.user_id == user.id,
                JobEvent.scheduled_for.is_not(None),
                Job.archived_at.is_(None),
            )
            .order_by(JobEvent.scheduled_for.asc())
            .limit(6)
        )
    ).all()
    activity = (
        await db.execute(
            select(JobEvent, Job)
            .join(Job, Job.id == JobEvent.job_id)
            .where(JobEvent.user_id == user.id)
            .order_by(JobEvent.occurred_at.desc())
            .limit(8)
        )
    ).all()
    now = datetime.now(UTC)
    return DashboardResponse.model_validate(
        {
            "user": {"display_name": user.display_name, "username": user.username},
            "counts": {
                "applications_tracked": applications or 0,
                "interviews_active": interviews or 0,
                "resources_total": resources or 0,
            },
            "upcoming": [
            {
                "kind": event.type,
                "at": event.scheduled_for.isoformat(),
                "allDay": event.all_day,
                "overdue": event.scheduled_for < now,
                "job": {"id": str(job.id), "company": job.company, "title": job.title},
                "eventId": str(event.id),
            }
            for event, job in upcoming
            ],
            "recent_activity": [
            {
                "id": str(event.id),
                "jobId": str(event.job_id),
                "type": event.type,
                "title": event.title,
                "notes": event.notes,
                "occurredAt": event.occurred_at.isoformat(),
                "scheduledFor": event.scheduled_for.isoformat() if event.scheduled_for else None,
                "allDay": event.all_day,
                "system": True,
                "calendarLinked": False,
                "createdAt": event.created_at.isoformat(),
                "job": {"id": str(job.id), "company": job.company, "title": job.title},
            }
            for event, job in activity
            ],
            "recent_resources": [
            {
                "id": str(resource.id),
                "title": resource.title,
                "category": resource.category,
                "sourceUrl": resource.source_url,
                "sourcePlatform": resource.source_platform,
                "description": resource.description,
                "tags": [],
                "isFavorite": resource.is_favorite,
                "isSavedForLater": resource.is_saved_for_later,
                "collectionIds": [],
                "verificationStatus": resource.verification_status,
                "createdAt": resource.created_at.isoformat(),
            }
            for resource in recent_resources
            ],
        }
    )
