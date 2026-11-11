import base64
import binascii
import json
from datetime import UTC, date, datetime
from typing import Annotated, Literal, TypedDict
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from sqlalchemy import delete, func, or_, select, tuple_

from hub.common.idempotency import find_replay, save_response
from hub.deps import CurrentUser, DbSession
from hub.models import Application, ExternalLink, Extraction, Job, JobEvent, JobTag, Tag, User
from hub.modules.jobs.schemas import (
    CreateEventRequest,
    CreateJobRequest,
    JobDetailResponse,
    JobEventResponse,
    JobPageResponse,
    JobStatus,
    JobSummaryResponse,
    UpdateEventRequest,
    UpdateJobRequest,
)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])
JobSort = Literal["newest", "oldest", "next_action"]


def _today(user: User) -> date:
    return datetime.now(ZoneInfo(user.timezone)).date()


class JobCursor(TypedDict):
    sort: JobSort
    id: str
    createdAt: str
    actionOn: str | None


def _status(application: Application | None) -> str:
    return application.status if application else "saved"


def _encode_cursor(
    sort: JobSort, job: Job, application: Application | None
) -> str:
    data: JobCursor = {
        "sort": sort,
        "id": str(job.id),
        "createdAt": job.created_at.isoformat(),
        "actionOn": None,
    }
    if sort == "next_action":
        action_on = (
            application.next_follow_up_on if application else None
        ) or job.deadline
        data["actionOn"] = action_on.isoformat() if action_on else None
    encoded = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def _decode_cursor(cursor: str, sort: JobSort) -> JobCursor:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        if not isinstance(data, dict):
            raise ValueError
        if (
            data.get("sort") != sort
            or not isinstance(data.get("id"), str)
            or not isinstance(data.get("createdAt"), str)
        ):
            raise ValueError
        action_on = data.get("actionOn")
        if action_on is not None and not isinstance(action_on, str):
            raise ValueError
        UUID(data["id"])
        datetime.fromisoformat(data["createdAt"])
        if sort == "next_action" and action_on is not None:
            date.fromisoformat(action_on)
        return {
            "sort": sort,
            "id": data["id"],
            "createdAt": data["createdAt"],
            "actionOn": action_on,
        }
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, binascii.Error):
        raise HTTPException(status_code=422, detail="Invalid cursor") from None


def _summary(
    job: Job, application: Application | None, tags: list[Tag] | None = None
) -> JobSummaryResponse:
    return JobSummaryResponse(
        id=job.id,
        company=job.company,
        title=job.title,
        location=job.location,
        employment_type=job.employment_type,
        work_mode=job.work_mode,
        status=_status(application),
        applied_on=application.applied_on if application else None,
        next_follow_up_on=application.next_follow_up_on if application else None,
        deadline=job.deadline,
        tags=[{"id": str(tag.id), "name": tag.name} for tag in tags or []],
        source_url=job.source_url,
        archived=job.archived_at is not None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


async def _find_job(db: DbSession, user_id: UUID, job_id: UUID) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == user_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def _detail(db: DbSession, job: Job) -> JobDetailResponse:
    application = (
        await db.execute(select(Application).where(Application.job_id == job.id))
    ).scalar_one_or_none()
    events = list(
        (
            await db.execute(
                select(JobEvent)
                .where(JobEvent.job_id == job.id)
                .order_by(JobEvent.occurred_at.asc())
            )
        ).scalars()
    )
    linked_event_ids = set(
        (
            await db.execute(
                select(ExternalLink.entity_id).where(
                    ExternalLink.user_id == job.user_id,
                    ExternalLink.entity_type == "job_event",
                    ExternalLink.provider == "google_calendar",
                    ExternalLink.entity_id.in_([event.id for event in events]),
                )
            )
        ).scalars()
    ) if events else set()
    tags = (
        await db.execute(
            select(Tag)
            .join(JobTag, JobTag.tag_id == Tag.id)
            .where(JobTag.job_id == job.id, Tag.user_id == job.user_id)
        )
    ).scalars()
    return JobDetailResponse(
        **_summary(job, application, list(tags)).model_dump(),
        external_job_id=job.external_job_id,
        description=job.description,
        requirements=job.requirements,
        notes=job.notes,
        application=application,
        timeline=[
            JobEventResponse.model_validate(event).model_copy(
                update={"calendar_linked": event.id in linked_event_ids}
            )
            for event in events
        ],
    )


@router.get("", response_model=JobPageResponse)
async def list_jobs(
    user: CurrentUser,
    db: DbSession,
    q: str | None = None,
    status_filter: Annotated[list[JobStatus] | None, Query(alias="status[]")] = None,
    company: str | None = None,
    location: str | None = None,
    tag_ids: Annotated[list[UUID] | None, Query(alias="tag[]")] = None,
    applied_from: Annotated[date | None, Query(alias="appliedFrom")] = None,
    applied_to: Annotated[date | None, Query(alias="appliedTo")] = None,
    follow_up_before: Annotated[date | None, Query(alias="followUpBefore")] = None,
    archived: bool = False,
    sort: JobSort = "newest",
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
) -> JobPageResponse:
    action_on = func.coalesce(Application.next_follow_up_on, Job.deadline)
    query = (
        select(Job, Application)
        .outerjoin(Application, Application.job_id == Job.id)
        .where(Job.user_id == user.id)
    )
    if not archived:
        query = query.where(Job.archived_at.is_(None))
    if q:
        pattern = f"%{q}%"
        query = query.where(Job.title.ilike(pattern) | Job.company.ilike(pattern))
    if company:
        query = query.where(Job.company.ilike(f"%{company}%"))
    if location:
        normalized_location = (
            "onsite" if location.strip().lower() in {"on-site", "onsite"} else location
        )
        query = query.where(
            or_(
                Job.location.ilike(f"%{location}%"),
                Job.work_mode.ilike(f"%{normalized_location}%"),
            )
        )
    status_values = status_filter or []
    if status_values:
        conditions = []
        if "saved" in status_values:
            conditions.append(Application.id.is_(None))
        applied_statuses = [value for value in status_values if value != "saved"]
        if applied_statuses:
            conditions.append(Application.status.in_(applied_statuses))
        query = query.where(or_(*conditions))
    if tag_ids:
        query = query.where(
            Job.id.in_(
                select(JobTag.job_id).where(JobTag.tag_id.in_(tag_ids))
            )
        )
    if applied_from:
        query = query.where(Application.applied_on >= applied_from)
    if applied_to:
        query = query.where(Application.applied_on <= applied_to)
    if follow_up_before:
        query = query.where(Application.next_follow_up_on <= follow_up_before)

    cursor_data = _decode_cursor(cursor, sort) if cursor else None
    if sort == "newest":
        query = query.order_by(Job.created_at.desc(), Job.id.desc())
        if cursor_data:
            created_at = datetime.fromisoformat(cursor_data["createdAt"])
            job_id = UUID(cursor_data["id"])
            query = query.where(tuple_(Job.created_at, Job.id) < (created_at, job_id))
    elif sort == "oldest":
        query = query.order_by(Job.created_at.asc(), Job.id.asc())
        if cursor_data:
            created_at = datetime.fromisoformat(cursor_data["createdAt"])
            job_id = UUID(cursor_data["id"])
            query = query.where(tuple_(Job.created_at, Job.id) > (created_at, job_id))
    else:
        query = query.order_by(
            action_on.asc().nulls_last(),
            Job.created_at.desc(),
            Job.id.desc(),
        )
        if cursor_data:
            created_at = datetime.fromisoformat(cursor_data["createdAt"])
            job_id = UUID(cursor_data["id"])
            action_value = cursor_data.get("actionOn")
            tie_breaker = or_(
                Job.created_at < created_at,
                (Job.created_at == created_at) & (Job.id < job_id),
            )
            if action_value is None:
                query = query.where(action_on.is_(None), tie_breaker)
            else:
                action_date = date.fromisoformat(action_value)
                query = query.where(
                    or_(
                        action_on > action_date,
                        (action_on == action_date) & tie_breaker,
                        action_on.is_(None),
                    )
                )
    rows = (await db.execute(query.limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    job_ids = [job.id for job, _ in rows]
    tag_rows = (
        await db.execute(
            select(JobTag.job_id, Tag.id, Tag.name)
            .join(Tag, Tag.id == JobTag.tag_id)
            .where(JobTag.job_id.in_(job_ids), Tag.user_id == user.id)
        )
    ).all() if job_ids else []
    tags_by_job: dict[UUID, list[dict[str, str]]] = {}
    for job_id, tag_id, tag_name in tag_rows:
        tags_by_job.setdefault(job_id, []).append(
            {"id": str(tag_id), "name": tag_name}
        )
    return JobPageResponse(
        items=[
            _summary(job, application, tags_by_job.get(job.id, []))
            for job, application in rows
        ],
        next_cursor=(
            _encode_cursor(sort, *rows[-1]) if has_more and rows else None
        ),
    )


@router.post("", response_model=JobDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: CreateJobRequest,
    user: CurrentUser,
    db: DbSession,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobDetailResponse:
    request_payload = payload.model_dump(mode="json")
    replay = await find_replay(
        db, user.id, idempotency_key, "POST", "/api/v1/jobs", request_payload, response
    )
    if replay is not None:
        return JobDetailResponse.model_validate(replay)
    job = Job(
        user_id=user.id,
        source_url=payload.source_url,
        company=payload.company,
        title=payload.title,
        location=payload.location,
        employment_type=payload.employment_type,
        work_mode=payload.work_mode,
        description=payload.description,
        requirements=payload.requirements,
        deadline=payload.deadline,
        notes=payload.notes,
        extraction_id=payload.extraction_id,
        field_provenance=payload.field_provenance,
    )
    db.add(job)
    await db.flush()
    application = None
    event_type = "saved"
    if payload.intent == "applied":
        application = Application(
            user_id=user.id,
            job_id=job.id,
            status="applied",
            applied_on=payload.applied_on or _today(user),
            next_follow_up_on=payload.next_follow_up_on,
        )
        db.add(application)
        await db.flush()
        event_type = "applied"
    db.add(
        JobEvent(
            user_id=user.id,
            job_id=job.id,
            application_id=application.id if application else None,
            type=event_type,
            title="Job applied" if application else "Job saved",
            occurred_at=datetime.now(UTC),
        )
    )
    if payload.extraction_id:
        extraction = (
            await db.execute(
                select(Extraction).where(
                    Extraction.id == payload.extraction_id,
                    Extraction.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if extraction is not None:
            extraction.status = "consumed"
    await db.commit()
    await db.refresh(job)
    detail = await _detail(db, job)
    await save_response(
        db,
        user.id,
        idempotency_key,
        "POST",
        "/api/v1/jobs",
        request_payload,
        status.HTTP_201_CREATED,
        detail.model_dump(mode="json", by_alias=True),
    )
    await db.commit()
    return detail


@router.get("/check-duplicate")
async def check_duplicate(
    url: str, user: CurrentUser, db: DbSession
) -> dict:
    job = (
        await db.execute(
            select(Job).where(Job.user_id == user.id, Job.source_url == url)
        )
    ).scalar_one_or_none()
    return {
        "duplicate": job is not None,
        "existing": (
            {"id": str(job.id), "company": job.company, "title": job.title}
            if job
            else None
        ),
    }


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: UUID, user: CurrentUser, db: DbSession) -> JobDetailResponse:
    return await _detail(db, await _find_job(db, user.id, job_id))


@router.patch("/{job_id}", response_model=JobDetailResponse)
async def update_job(
    job_id: UUID, payload: UpdateJobRequest, user: CurrentUser, db: DbSession
) -> JobDetailResponse:
    job = await _find_job(db, user.id, job_id)
    values = payload.model_dump(exclude_unset=True, exclude={"status", "archived"})
    for field, value in values.items():
        setattr(job, field, value)
    if payload.archived is not None:
        job.archived_at = datetime.now(UTC) if payload.archived else None
    if payload.status:
        application = (
            await db.execute(select(Application).where(Application.job_id == job.id))
        ).scalar_one_or_none()
        previous_status = _status(application)
        if payload.status == "saved" and application:
            raise HTTPException(status_code=409, detail="Cannot move an application back to saved")
        if payload.status != "saved" and application is None:
            application = Application(
                user_id=user.id,
                job_id=job.id,
                status=payload.status,
                applied_on=_today(user) if payload.status == "applied" else None,
            )
            db.add(application)
            await db.flush()
        elif application:
            application.status = payload.status
        if payload.status != previous_status:
            is_initial_application = (
                previous_status == "saved" and payload.status == "applied"
            )
            db.add(
                JobEvent(
                    user_id=user.id,
                    job_id=job.id,
                    application_id=application.id if application else None,
                    type="applied" if is_initial_application else "status_changed",
                    title="Job applied"
                    if is_initial_application
                    else f"Status changed to {payload.status.replace('_', ' ').title()}",
                    occurred_at=datetime.now(UTC),
                )
            )
    await db.commit()
    await db.refresh(job)
    return await _detail(db, job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: UUID, user: CurrentUser, db: DbSession) -> None:
    job = await _find_job(db, user.id, job_id)
    await db.execute(delete(Job).where(Job.id == job.id))
    await db.commit()


@router.post("/{job_id}/events", response_model=JobEventResponse, status_code=201)
async def create_event(
    job_id: UUID, payload: CreateEventRequest, user: CurrentUser, db: DbSession
) -> JobEventResponse:
    job = await _find_job(db, user.id, job_id)
    event = JobEvent(
        user_id=user.id,
        job_id=job.id,
        type=payload.type,
        title=payload.title,
        notes=payload.notes,
        occurred_at=payload.occurred_at or datetime.now(UTC),
        scheduled_for=payload.scheduled_for,
        all_day=payload.all_day,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return JobEventResponse.model_validate(event)


@router.patch("/{job_id}/events/{event_id}", response_model=JobEventResponse)
async def update_event(
    job_id: UUID,
    event_id: UUID,
    payload: UpdateEventRequest,
    user: CurrentUser,
    db: DbSession,
) -> JobEventResponse:
    await _find_job(db, user.id, job_id)
    event = (
        await db.execute(
            select(JobEvent).where(
                JobEvent.id == event_id,
                JobEvent.job_id == job_id,
                JobEvent.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    await db.commit()
    await db.refresh(event)
    return JobEventResponse.model_validate(event)


@router.delete("/{job_id}/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    job_id: UUID, event_id: UUID, user: CurrentUser, db: DbSession
) -> None:
    await _find_job(db, user.id, job_id)
    event = (
        await db.execute(
            select(JobEvent).where(
                JobEvent.id == event_id,
                JobEvent.job_id == job_id,
                JobEvent.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(event)
    await db.commit()
