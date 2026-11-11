from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hub.config import get_settings
from hub.deps import CurrentUser, DbSession
from hub.models import (
    Application,
    GmailProcessedMessage,
    GmailSyncRun,
    IntegrationConnection,
    Job,
    JobEvent,
)
from hub.modules.integrations.crypto import encrypt
from hub.modules.integrations.gmail import (
    JOB_SEARCH_TERMS,
    ParsedGmailMessage,
    classify_job_stage,
    match_job,
    parse_gmail_message,
)
from hub.modules.integrations.router import GOOGLE_AUTHORIZE_URL, _access_token
from hub.modules.integrations.schemas import (
    GmailReviewItem,
    GmailReviewList,
    GmailReviewRequest,
    GmailSyncRunResponse,
    OAuthStartResponse,
)

router = APIRouter(prefix="/api/v1/integrations/gmail", tags=["integrations"])
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
PAGE_SIZE = 5
PIPELINE_ORDER = {
    "saved": 0,
    "applied": 1,
    "assessment": 2,
    "interview": 3,
    "offer": 4,
}
CLOSED_STAGES = {"rejected", "withdrawn", "on_hold"}
EVENT_TYPE_BY_STATUS = {
    "applied": "applied",
    "assessment": "assessment",
    "interview": "interview",
    "offer": "offer",
    "rejected": "rejected",
}


class GmailHistoryExpired(Exception):
    pass


async def _gmail_connection(
    db: AsyncSession, user_id: UUID, *, lock: bool = False
) -> IntegrationConnection | None:
    query = select(IntegrationConnection).where(
        IntegrationConnection.user_id == user_id,
        IntegrationConnection.provider == "gmail",
    )
    if lock:
        query = query.with_for_update()
    return await db.scalar(query)


def _without_oauth_state(config: dict) -> dict:
    return {key: value for key, value in (config or {}).items() if key != "oauthState"}


def _sync_response(run: GmailSyncRun) -> GmailSyncRunResponse:
    return GmailSyncRunResponse.model_validate(run)


async def _gmail_get(
    client: httpx.AsyncClient,
    connection: IntegrationConnection,
    db: AsyncSession,
    access_token: str,
    path: str,
    *,
    params: dict[str, str | int] | None = None,
    missing_is_empty: bool = False,
) -> dict | None:
    try:
        result = await client.get(
            f"{GMAIL_API}/{path}",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=503, detail="Gmail is temporarily unavailable"
        ) from error

    if result.status_code == 404:
        if missing_is_empty:
            return None
        if path == "history":
            raise GmailHistoryExpired
        raise HTTPException(status_code=502, detail="Gmail returned an unavailable record")
    if result.status_code == 401:
        connection.status = "needs_reauth"
        connection.last_error = "Google authorization needs to be renewed"
        await db.commit()
        raise HTTPException(status_code=409, detail="Gmail needs reauthorization")
    if result.status_code == 403:
        connection.status = "error"
        connection.last_error = "Gmail access was denied; check the Gmail API and OAuth setup"
        await db.commit()
        raise HTTPException(
            status_code=502,
            detail="Gmail access was denied. Check the Gmail API and OAuth setup.",
        )
    if result.status_code == 429 or result.status_code >= 500:
        raise HTTPException(status_code=503, detail="Gmail is temporarily unavailable")
    if result.status_code != 200:
        raise HTTPException(status_code=502, detail="Gmail could not complete the request")
    return result.json()


def _gmail_search_query(after: date) -> str:
    terms = " ".join(JOB_SEARCH_TERMS)
    return f"after:{after:%Y/%m/%d} {{{terms}}}"


def _current_status(application: Application | None) -> str:
    return application.status if application else "saved"


def _can_auto_advance(current: str, target: str) -> bool:
    if current == target:
        return True
    if current in CLOSED_STAGES:
        return False
    if target in CLOSED_STAGES:
        return target == "rejected"
    return PIPELINE_ORDER.get(target, -1) > PIPELINE_ORDER.get(current, -1)


def _can_transition(current: str, target: str) -> bool:
    if current == target:
        return True
    if target == "saved":
        return current == "saved"
    if current in CLOSED_STAGES:
        return target in PIPELINE_ORDER and target != "saved"
    if target in CLOSED_STAGES:
        return True
    current_rank = PIPELINE_ORDER.get(current, -1)
    target_rank = PIPELINE_ORDER.get(target, -1)
    return target_rank > current_rank or target_rank == current_rank - 1


async def _apply_stage(
    db: AsyncSession,
    user,
    job: Job,
    application: Application | None,
    stage: str,
    message: ParsedGmailMessage,
    *,
    reviewed: bool,
) -> tuple[JobEvent, bool]:
    previous_status = _current_status(application)
    changed = previous_status != stage
    if application is None:
        applied_on = (
            message.received_at.astimezone(ZoneInfo(user.timezone)).date()
            if stage == "applied"
            else None
        )
        application = Application(
            user_id=user.id,
            job_id=job.id,
            status=stage,
            applied_on=applied_on,
        )
        db.add(application)
        await db.flush()
    elif changed:
        application.status = stage
        if stage == "applied" and application.applied_on is None:
            application.applied_on = message.received_at.astimezone(
                ZoneInfo(user.timezone)
            ).date()

    stage_title = stage.replace("_", " ").title()
    origin = "Reviewed from Gmail" if reviewed else "Detected from Gmail"
    event = JobEvent(
        user_id=user.id,
        job_id=job.id,
        application_id=application.id,
        type=EVENT_TYPE_BY_STATUS[stage],
        title=f"{stage_title} email received",
        notes=f'{origin}: "{message.subject}"'[:2000],
        occurred_at=message.received_at,
    )
    db.add(event)
    await db.flush()
    return event, changed


async def _process_message(
    db: AsyncSession,
    user,
    run: GmailSyncRun,
    message_id: str,
    access_token: str,
    client: httpx.AsyncClient,
    jobs: list[Job],
) -> None:
    run.messages_scanned += 1
    existing = await db.scalar(
        select(GmailProcessedMessage).where(
            GmailProcessedMessage.user_id == user.id,
            GmailProcessedMessage.message_id == message_id,
        )
    )
    if existing is not None:
        return

    connection = await _gmail_connection(db, user.id)
    if connection is None:
        raise HTTPException(status_code=409, detail="Gmail is not connected")
    raw_message = await _gmail_get(
        client,
        connection,
        db,
        access_token,
        f"messages/{message_id}",
        params={"format": "full"},
        missing_is_empty=True,
    )
    message = parse_gmail_message(raw_message) if raw_message else None
    if message is None:
        run.unmatched_discarded += 1
        return

    searchable_text = f"{message.subject}\n{message.sender or ''}\n{message.body_text}"
    job = match_job(searchable_text, jobs)
    if job is None:
        run.unmatched_discarded += 1
        return
    run.jobs_matched += 1

    stage = classify_job_stage(searchable_text)
    application = await db.scalar(
        select(Application).where(
            Application.user_id == user.id,
            Application.job_id == job.id,
        )
    )
    current = _current_status(application)
    if stage is None or not _can_auto_advance(current, stage):
        db.add(
            GmailProcessedMessage(
                user_id=user.id,
                message_id=message.message_id,
                thread_id=message.thread_id,
                job_id=job.id,
                sender=message.sender,
                subject=message.subject,
                received_at=message.received_at,
                suggested_status=stage,
                status="needs_review",
            )
        )
        run.review_queued += 1
        return

    event, changed = await _apply_stage(
        db, user, job, application, stage, message, reviewed=False
    )
    db.add(
        GmailProcessedMessage(
            user_id=user.id,
            message_id=message.message_id,
            thread_id=message.thread_id,
            job_id=job.id,
            event_id=event.id,
            sender=message.sender,
            subject=message.subject,
            received_at=message.received_at,
            suggested_status=stage,
            status="processed",
            processed_at=datetime.now(UTC),
        )
    )
    if changed:
        run.jobs_updated += 1


async def _process_ids(
    db: AsyncSession,
    user,
    run: GmailSyncRun,
    message_ids: list[str],
    access_token: str,
    client: httpx.AsyncClient,
) -> None:
    jobs = list(
        (
            await db.execute(
                select(Job).where(
                    Job.user_id == user.id,
                    Job.archived_at.is_(None),
                )
            )
        ).scalars()
    )
    for message_id in message_ids:
        await _process_message(
            db, user, run, message_id, access_token, client, jobs
        )


async def _profile(
    client: httpx.AsyncClient,
    connection: IntegrationConnection,
    db: AsyncSession,
    access_token: str,
) -> dict:
    result = await _gmail_get(
        client, connection, db, access_token, "profile"
    )
    if result is None:
        raise HTTPException(status_code=502, detail="Gmail profile could not be loaded")
    return result


async def _begin_initial_sync(
    run: GmailSyncRun,
    connection: IntegrationConnection,
    client: httpx.AsyncClient,
    db: AsyncSession,
    access_token: str,
) -> None:
    profile = await _profile(client, connection, db, access_token)
    history_id = profile.get("historyId")
    if not isinstance(history_id, str):
        raise HTTPException(status_code=502, detail="Gmail sync could not be initialized")
    run.mode = "initial"
    run.after_date = datetime.now(UTC).date() - timedelta(days=90)
    run.page_token = None
    run.history_page_token = None
    run.pending_message_ids = []
    run.start_history_id = history_id
    run.latest_history_id = history_id


def _history_message_ids(data: dict) -> list[str]:
    message_ids: list[str] = []
    for item in data.get("history", []):
        if not isinstance(item, dict):
            continue
        for added in item.get("messagesAdded", []):
            message = added.get("message") if isinstance(added, dict) else None
            message_id = message.get("id") if isinstance(message, dict) else None
            if isinstance(message_id, str):
                message_ids.append(message_id)
    return list(dict.fromkeys(message_ids))


def _finish_sync(
    run: GmailSyncRun, connection: IntegrationConnection
) -> None:
    now = datetime.now(UTC)
    run.status = "completed"
    run.finished_at = now
    config = _without_oauth_state(connection.config)
    config["historyId"] = run.latest_history_id or run.start_history_id
    config["lastSyncAt"] = now.isoformat()
    connection.config = config
    connection.last_used_at = now
    connection.last_error = None


async def _advance_initial_sync(
    db: AsyncSession,
    user,
    connection: IntegrationConnection,
    run: GmailSyncRun,
    client: httpx.AsyncClient,
    access_token: str,
) -> None:
    if run.start_history_id is None:
        await _begin_initial_sync(run, connection, client, db, access_token)
    params: dict[str, str | int] = {
        "maxResults": PAGE_SIZE,
        "q": _gmail_search_query(run.after_date or date.today()),
    }
    if run.page_token:
        params["pageToken"] = run.page_token
    data = await _gmail_get(
        client, connection, db, access_token, "messages", params=params
    )
    if data is None:
        raise HTTPException(status_code=502, detail="Gmail returned no message list")
    message_ids = [
        item["id"]
        for item in data.get("messages", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    await _process_ids(db, user, run, message_ids, access_token, client)
    run.page_token = data.get("nextPageToken")
    if not run.page_token:
        _finish_sync(run, connection)


async def _advance_incremental_sync(
    db: AsyncSession,
    user,
    connection: IntegrationConnection,
    run: GmailSyncRun,
    client: httpx.AsyncClient,
    access_token: str,
) -> None:
    if run.pending_message_ids:
        batch = run.pending_message_ids[:PAGE_SIZE]
        run.pending_message_ids = run.pending_message_ids[PAGE_SIZE:]
        await _process_ids(db, user, run, batch, access_token, client)
        if not run.pending_message_ids and not run.history_page_token:
            _finish_sync(run, connection)
        return

    params: dict[str, str | int] = {
        "startHistoryId": run.start_history_id or "",
        "maxResults": 100,
    }
    if run.history_page_token:
        params["pageToken"] = run.history_page_token
    data = await _gmail_get(
        client, connection, db, access_token, "history", params=params
    )
    if data is None:
        raise HTTPException(status_code=502, detail="Gmail returned no history")
    history_id = data.get("historyId")
    if isinstance(history_id, str):
        run.latest_history_id = history_id
    run.pending_message_ids = _history_message_ids(data)
    run.history_page_token = data.get("nextPageToken")
    if run.pending_message_ids:
        batch = run.pending_message_ids[:PAGE_SIZE]
        run.pending_message_ids = run.pending_message_ids[PAGE_SIZE:]
        await _process_ids(db, user, run, batch, access_token, client)
    if not run.pending_message_ids and not run.history_page_token:
        _finish_sync(run, connection)


@router.post("/oauth/start", response_model=OAuthStartResponse)
async def gmail_oauth_start(
    user: CurrentUser, db: DbSession
) -> OAuthStartResponse:
    settings = get_settings()
    if (
        not settings.google_client_id
        or not settings.google_client_secret
        or not settings.google_gmail_redirect_uri
    ):
        raise HTTPException(status_code=503, detail="Gmail OAuth is not configured")
    connection = await _gmail_connection(db, user.id, lock=True)
    if connection is None:
        connection = IntegrationConnection(user_id=user.id, provider="gmail")
        db.add(connection)
    previous_config = connection.config or {}
    state = uuid4().hex
    connection.status = "connecting"
    connection.last_error = None
    connection.config = {
        **{
            key: value
            for key, value in previous_config.items()
            if key in {"historyId", "lastSyncAt"}
        },
        "oauthState": state,
    }
    await db.commit()
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_gmail_redirect_uri,
            "response_type": "code",
            "scope": GMAIL_READONLY_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return OAuthStartResponse(auth_url=f"{GOOGLE_AUTHORIZE_URL}?{query}")


@router.get("/oauth/callback")
async def gmail_oauth_callback(
    db: DbSession,
    state: str = Query(min_length=1),
    code: str | None = None,
    error: str | None = None,
) -> Response:
    connection = await db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.provider == "gmail",
            IntegrationConnection.status == "connecting",
            IntegrationConnection.config["oauthState"].as_string() == state,
        )
    )
    settings = get_settings()
    if connection is None:
        raise HTTPException(status_code=400, detail="Invalid Gmail OAuth state")
    if error or not code:
        connection.status = "error"
        connection.last_error = "Gmail authorization was not completed"
        connection.config = _without_oauth_state(connection.config)
        await db.commit()
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": f"{settings.web_origin}/settings?gmail=cancelled"},
        )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_gmail_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_response.status_code != 200:
                connection.status = "error"
                connection.last_error = "Google did not authorize Gmail access"
                connection.config = _without_oauth_state(connection.config)
                await db.commit()
                raise HTTPException(
                    status_code=422, detail="Gmail authorization failed"
                )
            try:
                token = token_response.json()
            except ValueError as token_error:
                connection.status = "error"
                connection.last_error = "Google returned an invalid Gmail token response"
                connection.config = _without_oauth_state(connection.config)
                await db.commit()
                raise HTTPException(
                    status_code=502, detail="Gmail authorization failed"
                ) from token_error
            access_token = token.get("access_token")
            if not isinstance(access_token, str):
                connection.status = "error"
                connection.last_error = "Google returned an invalid Gmail token"
                connection.config = _without_oauth_state(connection.config)
                await db.commit()
                raise HTTPException(
                    status_code=422, detail="Gmail authorization failed"
                )
            profile_response = await client.get(
                f"{GMAIL_API}/profile",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.RequestError as request_error:
        connection.status = "error"
        connection.last_error = "Gmail could not be reached during authorization"
        connection.config = _without_oauth_state(connection.config)
        await db.commit()
        raise HTTPException(
            status_code=503, detail="Gmail could not be reached"
        ) from request_error

    if profile_response.status_code != 200:
        connection.status = "error"
        connection.last_error = "Gmail account details could not be verified"
        connection.config = _without_oauth_state(connection.config)
        await db.commit()
        raise HTTPException(status_code=502, detail="Gmail account could not be verified")
    refresh_token = token.get("refresh_token")
    if isinstance(refresh_token, str):
        connection.encrypted_credentials = encrypt(refresh_token)
    elif connection.encrypted_credentials is None:
        connection.status = "error"
        connection.last_error = "Google did not provide a refresh token"
        connection.config = _without_oauth_state(connection.config)
        await db.commit()
        raise HTTPException(
            status_code=422,
            detail="Google did not provide ongoing Gmail access. Reconnect and approve access.",
        )
    try:
        profile = profile_response.json()
    except ValueError as error:
        connection.status = "error"
        connection.last_error = "Gmail account details could not be verified"
        connection.config = _without_oauth_state(connection.config)
        await db.commit()
        raise HTTPException(
            status_code=502, detail="Gmail account could not be verified"
        ) from error
    email_address = profile.get("emailAddress")
    connection.status = "connected"
    connection.account_label = email_address if isinstance(email_address, str) else None
    connection.scopes = [GMAIL_READONLY_SCOPE]
    connection.config = {
        key: value
        for key, value in connection.config.items()
        if key in {"historyId", "lastSyncAt"}
    }
    connection.last_error = None
    connection.last_used_at = datetime.now(UTC)
    await db.commit()
    return Response(
        status_code=status.HTTP_302_FOUND,
        headers={"Location": f"{settings.web_origin}/settings?connected=gmail"},
    )


@router.post(
    "/sync",
    response_model=GmailSyncRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_gmail_sync(user: CurrentUser, db: DbSession) -> GmailSyncRunResponse:
    connection = await _gmail_connection(db, user.id, lock=True)
    if connection is None or connection.status != "connected":
        raise HTTPException(status_code=409, detail="Gmail is not connected")
    active = await db.scalar(
        select(GmailSyncRun).where(
            GmailSyncRun.user_id == user.id,
            GmailSyncRun.connection_id == connection.id,
            GmailSyncRun.status == "running",
        )
    )
    if active is not None:
        return _sync_response(active)

    has_cursor = isinstance(connection.config.get("historyId"), str)
    run = GmailSyncRun(
        user_id=user.id,
        connection_id=connection.id,
        mode="incremental" if has_cursor else "initial",
        status="running",
        after_date=None if has_cursor else datetime.now(UTC).date() - timedelta(days=90),
        start_history_id=connection.config.get("historyId") if has_cursor else None,
        latest_history_id=connection.config.get("historyId") if has_cursor else None,
    )
    db.add(run)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        active = await db.scalar(
            select(GmailSyncRun).where(
                GmailSyncRun.user_id == user.id,
                GmailSyncRun.connection_id == connection.id,
                GmailSyncRun.status == "running",
            )
        )
        if active is None:
            raise HTTPException(
                status_code=409, detail="A Gmail sync could not be started"
            ) from None
        return _sync_response(active)
    await db.refresh(run)
    return _sync_response(run)


@router.post("/sync/{run_id}/step", response_model=GmailSyncRunResponse)
async def advance_gmail_sync(
    run_id: UUID, user: CurrentUser, db: DbSession
) -> GmailSyncRunResponse:
    run = await db.scalar(
        select(GmailSyncRun)
        .where(
            GmailSyncRun.id == run_id,
            GmailSyncRun.user_id == user.id,
            GmailSyncRun.status == "running",
        )
        .with_for_update()
    )
    if run is None:
        completed = await db.scalar(
            select(GmailSyncRun).where(
                GmailSyncRun.id == run_id,
                GmailSyncRun.user_id == user.id,
            )
        )
        if completed is None:
            raise HTTPException(status_code=404, detail="Gmail sync run not found")
        return _sync_response(completed)
    connection = await _gmail_connection(db, user.id)
    if connection is None or connection.id != run.connection_id:
        raise HTTPException(status_code=409, detail="Gmail is not connected")
    try:
        access_token = await _access_token(connection, db)
        async with httpx.AsyncClient(timeout=10) as client:
            if run.mode == "initial":
                await _advance_initial_sync(
                    db, user, connection, run, client, access_token
                )
            else:
                try:
                    await _advance_incremental_sync(
                        db, user, connection, run, client, access_token
                    )
                except GmailHistoryExpired:
                    await _begin_initial_sync(
                        run, connection, client, db, access_token
                    )
    except HTTPException as error:
        if error.status_code >= 500:
            await db.rollback()
        raise
    except httpx.RequestError as error:
        await db.rollback()
        raise HTTPException(
            status_code=503, detail="Gmail is temporarily unavailable"
        ) from error
    await db.commit()
    await db.refresh(run)
    return _sync_response(run)


@router.get("/review", response_model=GmailReviewList)
async def list_gmail_reviews(
    user: CurrentUser, db: DbSession
) -> GmailReviewList:
    rows = await db.execute(
        select(GmailProcessedMessage, Job)
        .join(Job, Job.id == GmailProcessedMessage.job_id)
        .where(
            GmailProcessedMessage.user_id == user.id,
            GmailProcessedMessage.status == "needs_review",
            Job.user_id == user.id,
            Job.archived_at.is_(None),
        )
        .order_by(GmailProcessedMessage.received_at.desc())
        .limit(100)
    )
    return GmailReviewList(
        items=[
            GmailReviewItem(
                message_id=message.message_id,
                job_id=job.id,
                company=job.company,
                title=job.title,
                sender=message.sender,
                subject=message.subject,
                received_at=message.received_at,
                suggested_status=message.suggested_status,
            )
            for message, job in rows
        ]
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_gmail(user: CurrentUser, db: DbSession) -> Response:
    connection = await _gmail_connection(db, user.id)
    await db.execute(
        delete(GmailProcessedMessage).where(
            GmailProcessedMessage.user_id == user.id
        )
    )
    if connection is not None:
        await db.delete(connection)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/review/{message_id}")
async def resolve_gmail_review(
    message_id: str,
    payload: GmailReviewRequest,
    user: CurrentUser,
    db: DbSession,
) -> dict[str, str]:
    record = await db.scalar(
        select(GmailProcessedMessage)
        .where(
            GmailProcessedMessage.message_id == message_id,
            GmailProcessedMessage.user_id == user.id,
            GmailProcessedMessage.status == "needs_review",
        )
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Gmail review item not found")
    if payload.status == "ignore":
        record.status = "ignored"
        record.processed_at = datetime.now(UTC)
        await db.commit()
        return {"status": "ignored", "jobId": str(record.job_id)}

    job = await db.scalar(
        select(Job).where(
            Job.id == record.job_id,
            Job.user_id == user.id,
            Job.archived_at.is_(None),
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Matched job not found")
    application = await db.scalar(
        select(Application).where(
            Application.user_id == user.id,
            Application.job_id == job.id,
        )
    )
    current = _current_status(application)
    if not _can_transition(current, payload.status):
        raise HTTPException(status_code=409, detail="invalid_transition")
    message = ParsedGmailMessage(
        message_id=record.message_id,
        thread_id=record.thread_id,
        sender=record.sender,
        subject=record.subject,
        received_at=record.received_at,
        body_text="",
    )
    event, _ = await _apply_stage(
        db, user, job, application, payload.status, message, reviewed=True
    )
    record.event_id = event.id
    record.status = "processed"
    record.suggested_status = payload.status
    record.processed_at = datetime.now(UTC)
    await db.commit()
    return {"status": "processed", "jobId": str(job.id)}
