from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from sqlalchemy import select

from hub.common.idempotency import find_replay, save_response
from hub.config import get_settings
from hub.deps import CurrentUser, DbSession
from hub.models import (
    ExternalLink,
    IntegrationConnection,
    Job,
    JobEvent,
    Resource,
    ResourceTag,
    Tag,
)
from hub.modules.integrations.crypto import decrypt, encrypt
from hub.modules.integrations.schemas import (
    CalendarConfigRequest,
    CalendarEventRequest,
    CalendarEventResponse,
    CalendarList,
    DatabaseList,
    IntegrationList,
    IntegrationSummary,
    NotionConfigRequest,
    NotionConnectRequest,
    NotionExportRequest,
    NotionExportResponse,
    NotionExportResult,
    OAuthStartResponse,
)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])
NOTION_VERSION = "2026-03-11"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
NOTION_CATEGORY_LABELS = {
    "ai_tool": "AI Tools",
    "course": "Courses",
    "certification": "Certifications",
    "research": "Research",
    "article": "Articles",
    "developer_resource": "Developer Resources",
    "other": "Other",
}


async def _access_token(connection: IntegrationConnection, db: DbSession) -> str:
    if connection.provider == "notion":
        if not connection.encrypted_credentials:
            raise HTTPException(status_code=409, detail="Integration is not connected")
        return decrypt(connection.encrypted_credentials)
    if not connection.encrypted_credentials:
        raise HTTPException(status_code=409, detail="Integration is not connected")
    settings = get_settings()
    integration_name = "Gmail" if connection.provider == "gmail" else "Google Calendar"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            result = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": decrypt(connection.encrypted_credentials),
                    "grant_type": "refresh_token",
                },
            )
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=503, detail=f"{integration_name} is temporarily unavailable"
        ) from error
    if result.status_code != 200:
        connection.status = "needs_reauth"
        connection.last_error = "Google authorization needs to be renewed"
        await db.commit()
        raise HTTPException(
            status_code=409, detail=f"{integration_name} needs reauthorization"
        )
    access_token = result.json().get("access_token")
    if not isinstance(access_token, str):
        raise HTTPException(
            status_code=502, detail=f"{integration_name} returned an invalid token"
        )
    return access_token


async def _connection(
    db: DbSession, user_id, provider: str
) -> IntegrationConnection | None:
    return (
        await db.execute(
            select(IntegrationConnection).where(
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.provider == provider,
            )
        )
    ).scalar_one_or_none()


def _summary(connection: IntegrationConnection) -> IntegrationSummary:
    return IntegrationSummary(
        id=connection.id,
        provider=connection.provider,
        status=connection.status,
        account_label=connection.account_label,
        config={
            key: value
            for key, value in connection.config.items()
            if key not in {"oauthState", "historyId"}
        },
        scopes=connection.scopes,
        last_used_at=connection.last_used_at,
        last_error=connection.last_error,
    )


def _notion_blocks(resource: Resource) -> list[dict]:
    text = "\n\n".join(
        value
        for value in (resource.description, resource.summary, resource.notes)
        if value
    )
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text[index : index + 1900]}}]
            },
        }
        for index in range(0, len(text), 1900)
    ]


def _notion_database_items(results: list[dict]) -> list[dict[str, str]]:
    items = []
    for item in results:
        if item.get("object") != "data_source":
            continue
        title = "".join(
            part.get("plain_text", "") for part in item.get("title", [])
        )
        items.append(
            {
                "id": item["id"],
                "title": title or "Untitled database",
            }
        )
    return items


def _notion_category_label(category: str) -> str:
    return NOTION_CATEGORY_LABELS.get(category, category)


def _google_event_body(payload: CalendarEventRequest, job: Job | None) -> dict[str, object]:
    body: dict[str, object] = {
        "summary": payload.title
        or (f"{job.title} — {job.company}" if job is not None else ""),
        "description": payload.description
        if payload.description is not None
        else (job.source_url or "" if job is not None else ""),
        "location": payload.location or "",
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": reminder.method, "minutes": reminder.minutes}
                for reminder in payload.reminders
            ],
        },
    }
    if payload.all_day:
        body["start"] = {"date": payload.starts_at.date().isoformat()}
        end_date = (payload.ends_at or payload.starts_at).date() + timedelta(days=1)
        body["end"] = {"date": end_date.isoformat()}
    else:
        end_time = payload.ends_at or payload.starts_at + timedelta(hours=1)
        body["start"] = {
            "dateTime": payload.starts_at.isoformat(),
            "timeZone": payload.time_zone,
        }
        body["end"] = {
            "dateTime": end_time.isoformat(),
            "timeZone": payload.time_zone,
        }
    return body


async def _ensure_notion_tag_options(
    client: httpx.AsyncClient,
    token: str,
    data_source_id: str,
    tag_names: list[str],
) -> None:
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}
    result = await client.get(
        f"https://api.notion.com/v1/data_sources/{data_source_id}",
        headers=headers,
    )
    if result.status_code != 200:
        raise RuntimeError("Notion tag options could not be read")
    tag_property = result.json().get("properties", {}).get("Tags")
    if not tag_property or tag_property.get("type") != "multi_select":
        raise RuntimeError("The Notion Tags property is no longer a multi-select field")
    options = tag_property.get("multi_select", {}).get("options", [])
    existing = {option.get("name", "").casefold() for option in options}
    missing = [name for name in tag_names if name.casefold() not in existing]
    if not missing:
        return
    kept_options = [
        {"id": option["id"]}
        for option in options
        if isinstance(option.get("id"), str)
    ]
    update = await client.patch(
        f"https://api.notion.com/v1/data_sources/{data_source_id}",
        headers=headers,
        json={
            "properties": {
                "Tags": {
                    "multi_select": {
                        "options": kept_options + [{"name": name} for name in missing]
                    }
                }
            }
        },
    )
    if update.status_code != 200:
        raise RuntimeError("Notion could not add the resource's tag options")


async def _sync_notion_blocks(
    client: httpx.AsyncClient,
    token: str,
    page_id: str,
    blocks: list[dict],
    current_ids: list[str],
) -> list[str]:
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}
    synced_ids: list[str] = []
    for index, block in enumerate(blocks):
        block_data = {block["type"]: block[block["type"]]}
        if index < len(current_ids):
            result = await client.patch(
                f"https://api.notion.com/v1/blocks/{current_ids[index]}",
                headers=headers,
                json=block_data,
            )
            if result.status_code != 200:
                raise RuntimeError("Notion could not update a resource content block")
            synced_ids.append(current_ids[index])
        else:
            result = await client.patch(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers=headers,
                json={"children": [block]},
            )
            if result.status_code != 200:
                raise RuntimeError("Notion could not add a resource content block")
            synced_ids.append(result.json()["results"][0]["id"])
    for block_id in current_ids[len(blocks) :]:
        result = await client.delete(
            f"https://api.notion.com/v1/blocks/{block_id}",
            headers=headers,
        )
        if result.status_code != 200:
            raise RuntimeError("Notion could not remove an outdated resource content block")
    return synced_ids


@router.get("", response_model=IntegrationList)
async def list_integrations(user: CurrentUser, db: DbSession) -> IntegrationList:
    rows = (
        await db.execute(
            select(IntegrationConnection).where(IntegrationConnection.user_id == user.id)
        )
    ).scalars()
    return IntegrationList(items=[_summary(row) for row in rows])


@router.post("/notion/connect", response_model=IntegrationSummary)
async def connect_notion(
    payload: NotionConnectRequest, user: CurrentUser, db: DbSession
) -> IntegrationSummary:
    token = payload.token or get_settings().notion_token
    if not token:
        raise HTTPException(
            status_code=422,
            detail="Paste a Notion token or configure NOTION_TOKEN on the API server",
        )
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            result = await client.get(
                "https://api.notion.com/v1/users/me",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Notion-Version": NOTION_VERSION,
                },
            )
    except httpx.RequestError as error:
        raise HTTPException(status_code=503, detail="Notion could not be reached") from error
    if result.status_code != 200:
        raise HTTPException(status_code=422, detail="Notion token was rejected")
    body = result.json()
    connection = await _connection(db, user.id, "notion")
    if connection is None:
        connection = IntegrationConnection(user_id=user.id, provider="notion")
        db.add(connection)
    connection.status = "connected"
    connection.encrypted_credentials = encrypt(token)
    connection.account_label = body.get("name") or body.get("person", {}).get("email")
    connection.scopes = []
    connection.config = {}
    connection.last_error = None
    await db.commit()
    await db.refresh(connection)
    return _summary(connection)


@router.get("/notion/databases", response_model=DatabaseList)
async def notion_databases(
    user: CurrentUser, db: DbSession, q: str | None = Query(default=None)
) -> DatabaseList:
    connection = await _connection(db, user.id, "notion")
    if connection is None:
        raise HTTPException(status_code=409, detail="Notion is not connected")
    body = {"filter": {"property": "object", "value": "data_source"}}
    if q:
        body["query"] = q
    token = await _access_token(connection, db)
    async with httpx.AsyncClient(timeout=10) as client:
        result = await client.post(
            "https://api.notion.com/v1/search",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION},
            json=body,
        )
    if result.status_code != 200:
        raise HTTPException(status_code=502, detail="Notion databases could not be loaded")
    return DatabaseList(items=_notion_database_items(result.json().get("results", [])))


@router.put("/notion/config", response_model=IntegrationSummary)
async def configure_notion(
    payload: NotionConfigRequest, user: CurrentUser, db: DbSession
) -> IntegrationSummary:
    connection = await _connection(db, user.id, "notion")
    if connection is None:
        raise HTTPException(status_code=409, detail="Notion is not connected")
    token = await _access_token(connection, db)
    async with httpx.AsyncClient(timeout=10) as client:
        result = await client.get(
            f"https://api.notion.com/v1/data_sources/{payload.data_source_id}",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION},
        )
    if result.status_code != 200:
        raise HTTPException(status_code=422, detail="That Notion database source is not accessible")
    properties = result.json().get("properties", {})
    title_property = next(
        (name for name, value in properties.items() if value.get("type") == "title"),
        None,
    )
    category_property = properties.get("Category")
    if (
        title_property is None
        or category_property is None
        or category_property.get("type") != "select"
    ):
        raise HTTPException(
            status_code=422,
            detail="The data source needs a title property and a Category select property.",
        )
    existing_categories = {
        option.get("name", "").casefold()
        for option in category_property.get("select", {}).get("options", [])
    }
    missing_categories = [
        label
        for label in NOTION_CATEGORY_LABELS.values()
        if label.casefold() not in existing_categories
    ]
    if missing_categories:
        raise HTTPException(
            status_code=422,
            detail=f"Add these options to Category: {', '.join(missing_categories)}.",
        )
    source_url_property = properties.get("Source URL")
    if source_url_property is not None and source_url_property.get("type") != "url":
        raise HTTPException(
            status_code=422,
            detail="The Source URL property must use the URL type.",
        )
    optional_properties = {
        "Description": "rich_text",
        "Date added": "date",
        "Tags": "multi_select",
    }
    for property_name, expected_type in optional_properties.items():
        prop = properties.get(property_name)
        if prop is not None and prop.get("type") != expected_type:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"The {property_name} property must use the "
                    f"{expected_type.replace('_', ' ')} type."
                ),
            )
    connection.config = {
        "dataSourceId": payload.data_source_id,
        "titleProperty": title_property,
        "categoryProperty": "Category",
        "sourceUrlProperty": "Source URL" if source_url_property else None,
        "descriptionProperty": "Description" if properties.get("Description") else None,
        "dateAddedProperty": "Date added" if properties.get("Date added") else None,
        "tagsProperty": "Tags" if properties.get("Tags") else None,
    }
    await db.commit()
    await db.refresh(connection)
    return _summary(connection)


@router.post("/notion/export", response_model=NotionExportResponse)
async def export_notion(
    payload: NotionExportRequest,
    user: CurrentUser,
    db: DbSession,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> NotionExportResponse:
    request_payload = payload.model_dump(mode="json")
    replay = await find_replay(
        db,
        user.id,
        idempotency_key,
        "POST",
        "/api/v1/integrations/notion/export",
        request_payload,
        response,
    )
    if replay is not None:
        return NotionExportResponse.model_validate(replay)
    connection = await _connection(db, user.id, "notion")
    if connection is None or not connection.config.get("dataSourceId"):
        raise HTTPException(status_code=409, detail="Choose a Notion database first")
    token = await _access_token(connection, db)
    results: list[NotionExportResult] = []
    tag_names: dict[UUID, list[str]] = {}
    if "Tags" in connection.config:
        rows = await db.execute(
            select(ResourceTag.resource_id, Tag.name)
            .join(Tag, Tag.id == ResourceTag.tag_id)
            .where(
                ResourceTag.resource_id.in_(payload.resource_ids),
                Tag.user_id == user.id,
            )
        )
        for resource_id, tag_name in rows:
            tag_names.setdefault(resource_id, []).append(tag_name)
    tag_options_error = None
    requested_tags = sorted({name for names in tag_names.values() for name in names})
    if connection.config.get("tagsProperty") and requested_tags:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await _ensure_notion_tag_options(
                    client,
                    token,
                    connection.config["dataSourceId"],
                    requested_tags,
                )
        except (httpx.RequestError, RuntimeError) as error:
            tag_options_error = str(error)
    for resource_id in payload.resource_ids:
        resource = await db.scalar(
            select(Resource).where(Resource.id == resource_id, Resource.user_id == user.id)
        )
        if resource is None:
            results.append(
                NotionExportResult(
                    resource_id=resource_id,
                    status="failed",
                    error="Resource not found",
                )
            )
            continue
        if tag_names.get(resource.id) and tag_options_error:
            results.append(
                NotionExportResult(
                    resource_id=resource.id,
                    status="failed",
                    error=tag_options_error,
                )
            )
            continue
        link = await db.scalar(
            select(ExternalLink).where(
                ExternalLink.user_id == user.id,
                ExternalLink.entity_type == "resource",
                ExternalLink.entity_id == resource.id,
                ExternalLink.provider == "notion",
            )
        )
        properties = {
            connection.config["titleProperty"]: {
                "title": [{"text": {"content": resource.title[:2000]}}]
            },
            connection.config["categoryProperty"]: {
                "select": {"name": _notion_category_label(resource.category)}
            },
        }
        source_url_property = connection.config.get("sourceUrlProperty")
        if resource.source_url and source_url_property:
            properties[source_url_property] = {"url": resource.source_url}
        description_property = connection.config.get("descriptionProperty")
        if description_property and resource.description:
            properties[description_property] = {
                "rich_text": [{"text": {"content": resource.description[:2000]}}]
            }
        date_added_property = connection.config.get("dateAddedProperty")
        if date_added_property:
            properties[date_added_property] = {
                "date": {"start": resource.created_at.date().isoformat()}
            }
        tags_property = connection.config.get("tagsProperty")
        if tags_property and tag_names.get(resource.id):
            properties[tags_property] = {
                "multi_select": [{"name": name} for name in tag_names[resource.id]]
            }
        body = {
            "parent": {
                "type": "data_source_id",
                "data_source_id": connection.config["dataSourceId"],
            },
            "properties": properties,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                if link:
                    result = await client.patch(
                        f"https://api.notion.com/v1/pages/{link.external_id}",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Notion-Version": NOTION_VERSION,
                        },
                        json={"properties": properties},
                    )
                    action = "updated"
                else:
                    result = await client.post(
                        "https://api.notion.com/v1/pages",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Notion-Version": NOTION_VERSION,
                        },
                        json=body,
                    )
                    action = "created"
                if result.status_code not in {200, 201}:
                    raise RuntimeError("Notion rejected the resource")
                data = result.json()
                if link is None:
                    link = ExternalLink(
                        user_id=user.id,
                        entity_type="resource",
                        entity_id=resource.id,
                        provider="notion",
                        external_id=data["id"],
                        external_url=data.get("url"),
                        last_synced_at=datetime.now(UTC),
                    )
                    db.add(link)
                    await db.commit()
                block_ids = await _sync_notion_blocks(
                    client,
                    token,
                    link.external_id,
                    _notion_blocks(resource),
                    link.link_metadata.get("contentBlockIds", []),
                )
                link.link_metadata = {"contentBlockIds": block_ids}
                link.last_synced_at = datetime.now(UTC)
                await db.commit()
            results.append(
                NotionExportResult(
                    resource_id=resource.id,
                    status=action,
                    notion_url=data.get("url"),
                )
            )
        except (httpx.RequestError, RuntimeError) as error:
            results.append(
                NotionExportResult(resource_id=resource.id, status="failed", error=str(error))
            )
    connection.last_used_at = datetime.now(UTC)
    export_response = NotionExportResponse(results=results)
    await save_response(
        db,
        user.id,
        idempotency_key,
        "POST",
        "/api/v1/integrations/notion/export",
        request_payload,
        status.HTTP_200_OK,
        export_response.model_dump(mode="json", by_alias=True),
    )
    await db.commit()
    return export_response


@router.get("/google-calendar/oauth/start", response_model=OAuthStartResponse)
async def google_oauth_start(user: CurrentUser, db: DbSession) -> OAuthStartResponse:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_redirect_uri:
        raise HTTPException(status_code=503, detail="Google Calendar is not configured")
    state = uuid4().hex
    connection = await _connection(db, user.id, "google_calendar")
    if connection is None:
        connection = IntegrationConnection(user_id=user.id, provider="google_calendar")
        db.add(connection)
    connection.status = "connecting"
    connection.config = {"oauthState": state}
    await db.commit()
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/calendar.calendarlist.readonly https://www.googleapis.com/auth/calendar.events",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return OAuthStartResponse(auth_url=f"{GOOGLE_AUTHORIZE_URL}?{query}")


@router.get("/google-calendar/oauth/callback")
async def google_oauth_callback(
    db: DbSession,
    code: str = Query(min_length=1),
    state: str = Query(min_length=1),
) -> Response:
    connection = (
        await db.execute(
            select(IntegrationConnection).where(
                IntegrationConnection.provider == "google_calendar",
                IntegrationConnection.status == "connecting",
                IntegrationConnection.config["oauthState"].as_string() == state,
            )
        )
    ).scalar_one_or_none()
    if connection is None:
        raise HTTPException(status_code=400, detail="Invalid Google OAuth state")
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        result = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if result.status_code != 200:
        connection.status = "error"
        connection.last_error = "Google authorization failed"
        await db.commit()
        raise HTTPException(status_code=422, detail="Google authorization failed")
    token = result.json()
    connection.status = "connected"
    connection.encrypted_credentials = encrypt(token["refresh_token"])
    connection.scopes = token.get("scope", "").split()
    connection.config = {}
    connection.last_error = None
    connection.last_used_at = datetime.now(UTC)
    await db.commit()
    return Response(
        status_code=status.HTTP_302_FOUND,
        headers={"Location": f"{settings.web_origin}/settings?connected=google_calendar"},
    )


@router.get("/google-calendar/calendars", response_model=CalendarList)
async def google_calendars(user: CurrentUser, db: DbSession) -> CalendarList:
    connection = await _connection(db, user.id, "google_calendar")
    if connection is None:
        raise HTTPException(status_code=409, detail="Google Calendar is not connected")
    token = await _access_token(connection, db)
    async with httpx.AsyncClient(timeout=10) as client:
        result = await client.get(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList",
            headers={"Authorization": f"Bearer {token}"},
        )
    if result.status_code != 200:
        raise HTTPException(status_code=502, detail="Google calendars could not be loaded")
    return CalendarList(
        items=[
            {
                "id": item["id"],
                "name": item.get("summary", item["id"]),
                "primary": item.get("primary", False),
            }
            for item in result.json().get("items", [])
        ]
    )


@router.put("/google-calendar/config", response_model=IntegrationSummary)
async def configure_google_calendar(
    payload: CalendarConfigRequest, user: CurrentUser, db: DbSession
) -> IntegrationSummary:
    connection = await _connection(db, user.id, "google_calendar")
    if connection is None:
        raise HTTPException(status_code=409, detail="Google Calendar is not connected")
    connection.config = {"calendarId": payload.calendar_id}
    await db.commit()
    await db.refresh(connection)
    return _summary(connection)


@router.post("/google-calendar/events", response_model=CalendarEventResponse, status_code=201)
async def create_google_event(
    payload: CalendarEventRequest,
    user: CurrentUser,
    db: DbSession,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CalendarEventResponse:
    request_payload = payload.model_dump(mode="json")
    replay = await find_replay(
        db,
        user.id,
        idempotency_key,
        "POST",
        "/api/v1/integrations/google-calendar/events",
        request_payload,
        response,
    )
    if replay is not None:
        return CalendarEventResponse.model_validate(replay)
    connection = await _connection(db, user.id, "google_calendar")
    if connection is None or not connection.config.get("calendarId"):
        raise HTTPException(status_code=409, detail="Choose a Google Calendar first")
    job = None
    if payload.job_id is not None:
        job = await db.scalar(
            select(Job).where(Job.id == payload.job_id, Job.user_id == user.id)
        )
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
    event = None
    if payload.job_event_id is not None:
        event = await db.scalar(
            select(JobEvent).where(
                JobEvent.id == payload.job_event_id,
                JobEvent.job_id == payload.job_id,
                JobEvent.user_id == user.id,
            )
        )
        if event is None:
            raise HTTPException(status_code=404, detail="Job timeline event not found")
    body = _google_event_body(payload, job)
    link = None
    if event is not None:
        link = await db.scalar(
            select(ExternalLink).where(
                ExternalLink.user_id == user.id,
                ExternalLink.entity_type == "job_event",
                ExternalLink.entity_id == event.id,
                ExternalLink.provider == "google_calendar",
            )
        )
    calendar_id = connection.config["calendarId"]
    token = await _access_token(connection, db)
    async with httpx.AsyncClient(timeout=15) as client:
        result = await (
            client.patch(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{link.external_id}",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
            if link
            else client.post(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
        )
    if result.status_code not in {200, 201}:
        raise HTTPException(status_code=502, detail="Google Calendar rejected the event")
    data = result.json()
    if link:
        link.last_synced_at = datetime.now(UTC)
    elif event is not None:
        db.add(
            ExternalLink(
                user_id=user.id,
                entity_type="job_event",
                entity_id=event.id,
                provider="google_calendar",
                external_id=data["id"],
                external_url=data.get("htmlLink"),
                last_synced_at=datetime.now(UTC),
            )
        )
    event_response = CalendarEventResponse(
        calendar_event_id=data["id"],
        html_link=data.get("htmlLink"),
    )
    await save_response(
        db,
        user.id,
        idempotency_key,
        "POST",
        "/api/v1/integrations/google-calendar/events",
        request_payload,
        status.HTTP_201_CREATED,
        event_response.model_dump(mode="json", by_alias=True),
    )
    await db.commit()
    return event_response


@router.delete("/google-calendar/events/{job_event_id}", status_code=204)
async def delete_google_event(job_event_id: UUID, user: CurrentUser, db: DbSession) -> Response:
    connection = await _connection(db, user.id, "google_calendar")
    if connection is None or not connection.config.get("calendarId"):
        raise HTTPException(status_code=409, detail="Google Calendar is not connected")
    link = await db.scalar(
        select(ExternalLink).where(
            ExternalLink.user_id == user.id,
            ExternalLink.entity_type == "job_event",
            ExternalLink.entity_id == job_event_id,
            ExternalLink.provider == "google_calendar",
        )
    )
    if link:
        token = await _access_token(connection, db)
        async with httpx.AsyncClient(timeout=10) as client:
            result = await client.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/{connection.config['calendarId']}/events/{link.external_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if result.status_code not in {200, 204, 404}:
            raise HTTPException(status_code=502, detail="Google Calendar rejected the deletion")
        await db.delete(link)
        await db.commit()
    return Response(status_code=204)


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(
    provider: str, user: CurrentUser, db: DbSession
) -> None:
    connection = await _connection(db, user.id, provider)
    if connection is None:
        return
    await db.delete(connection)
    await db.commit()
