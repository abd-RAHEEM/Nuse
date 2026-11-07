from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from urllib.parse import urlparse, urlunparse
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Response, status
from sqlalchemy import select

from hub.common.idempotency import find_replay, save_response
from hub.deps import CurrentUser, DbSession
from hub.models import Extraction, Job, Resource
from hub.modules.capture.fetcher import FetchError, fetch_page
from hub.modules.capture.providers import parse_document
from hub.modules.capture.schemas import CreateExtractionRequest, ExtractionResponse

router = APIRouter(prefix="/api/v1/extractions", tags=["capture"])


def normalize_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    hostname = parsed.hostname
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username
        or parsed.password
        or not hostname
    ):
        raise HTTPException(
            status_code=422, detail="Only public http(s) URLs are supported"
        )
    try:
        address = ip_address(hostname)
    except ValueError:
        address = None
    if (
        address is not None
        and (address.is_private or address.is_loopback or address.is_link_local
             or address.is_reserved or address.is_multicast)
    ) or hostname.lower() in {"localhost", "localhost.localdomain"} or hostname.lower().endswith(
        (".localhost", ".local")
    ):
        raise HTTPException(
            status_code=422,
            detail="unsafe_url: private and local network URLs cannot be fetched",
        )
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=hostname.lower() + (f":{parsed.port}" if parsed.port else ""),
        fragment="",
    )
    return value, urlunparse(normalized).rstrip("/")


def source_kind(domain: str | None) -> str:
    if not domain:
        return "other"
    if "linkedin.com" in domain:
        return "linkedin"
    if "instagram.com" in domain:
        return "instagram"
    if "github.com" in domain:
        return "github"
    return "other"


def build_result(payload: CreateExtractionRequest, normalized: str | None) -> dict:
    text = (payload.text or "").strip()
    first_line = text.splitlines()[0].strip() if text else ""
    if payload.type == "job":
        return {
            "type": "job",
            "company": {"value": None, "provenance": "not_found"},
            "title": {
                "value": first_line or None,
                "provenance": "extracted" if first_line else "not_found",
                "source": "plain_text",
            },
            "location": {"value": None, "provenance": "not_found"},
            "employmentType": {"value": None, "provenance": "not_found"},
            "workMode": {"value": None, "provenance": "not_found"},
            "externalJobId": {"value": None, "provenance": "not_found"},
            "description": {
                "value": text or None,
                "provenance": "extracted" if text else "not_found",
                "source": "plain_text",
            },
            "requirements": {"value": None, "provenance": "not_found"},
            "deadline": {"value": None, "provenance": "not_found"},
            "sourceUrl": {
                "value": payload.url,
                "provenance": "extracted" if payload.url else "not_found",
            },
        }
    return {
        "type": "resource",
        "title": {
            "value": first_line or None,
            "provenance": "extracted" if first_line else "not_found",
            "source": "plain_text",
        },
        "category": {"value": "other", "provenance": "suggested"},
        "sourcePlatform": {"value": None, "provenance": "not_found"},
        "description": {
            "value": text or None,
            "provenance": "extracted" if text else "not_found",
            "source": "plain_text",
        },
        "summary": {"value": None, "provenance": "not_found"},
        "suggestedTags": {"value": [], "provenance": "not_found"},
        "details": {"value": None, "provenance": "not_found"},
        "sourceUrl": {
            "value": payload.url,
            "provenance": "extracted" if payload.url else "not_found",
        },
    }


def response(extraction: Extraction, duplicate: dict | None = None) -> ExtractionResponse:
    domain = extraction.detected_domain
    restricted = extraction.detected_source_kind in {"linkedin", "instagram"}
    return ExtractionResponse(
        id=extraction.id,
        type=extraction.type,
        status=extraction.status,
        input={
            "url": extraction.input_url,
            "normalizedUrl": extraction.normalized_url,
            "hasText": bool(extraction.input_text),
        },
        detected_source={"kind": extraction.detected_source_kind, "domain": domain},
        detected_type=extraction.detected_type or "unknown",
        steps=[
            {
                "key": "fetch",
                "state": (
                    "skipped"
                    if not extraction.input_url or restricted
                    else "done" if extraction.provider_trace.get("fetch") == "done" else "failed"
                ),
            },
            {"key": "read", "state": "done" if extraction.result else "pending"},
            {"key": "structure", "state": "done" if extraction.result else "failed"},
        ],
        result=extraction.result,
        error=(
            {
                "code": "extraction_blocked",
                "message": (
                    "This source cannot be read automatically. "
                    "Paste its text to structure it."
                ),
                "hint": "paste_text",
            }
            if restricted and not extraction.input_text
            else (
                {
                    "code": extraction.error_code,
                    "message": extraction.error_message,
                    "hint": (
                        "check_url"
                        if extraction.error_code == "unsafe_url"
                        else "retry"
                    ),
                }
                if extraction.error_code
                else None
            )
        ),
        duplicate_of=duplicate,
        created_at=extraction.created_at,
        finished_at=extraction.finished_at,
    )


@router.post("", response_model=ExtractionResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_extraction(
    payload: CreateExtractionRequest,
    user: CurrentUser,
    db: DbSession,
    http_response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ExtractionResponse:
    request_payload = payload.model_dump(mode="json", by_alias=True)
    replay = await find_replay(
        db,
        user.id,
        idempotency_key,
        "POST",
        "/api/v1/extractions",
        request_payload,
        http_response,
    )
    if replay is not None:
        return ExtractionResponse.model_validate(replay)
    input_url = None
    normalized = None
    domain = None
    kind = "other"
    if payload.url:
        input_url, normalized = normalize_url(payload.url)
        parsed = urlparse(normalized)
        domain = parsed.hostname
        kind = source_kind(domain)
    duplicate = None
    model = Job if payload.type == "job" else Resource
    if normalized:
        existing = (
            await db.execute(
                select(model).where(
                    model.user_id == user.id, model.normalized_url == normalized
                )
            )
        ).scalar_one_or_none()
        if existing:
            duplicate = {"kind": payload.type, "id": str(existing.id), "title": existing.title}
    fetched = None
    fetch_error: FetchError | None = None
    if input_url and not payload.text and kind not in {"linkedin", "instagram"}:
        try:
            fetched = await fetch_page(input_url)
        except FetchError as error:
            if error.code == "unsafe_url":
                raise HTTPException(status_code=422, detail=f"unsafe_url: {error}") from error
            fetch_error = error
    now = datetime.now(UTC)
    effective_payload = payload
    if fetched:
        effective_payload = payload.model_copy(update={"text": fetched.body, "url": input_url})
    has_result = bool(fetched or payload.text or kind in {"linkedin", "instagram"})
    parsed_result = (
        parse_document(effective_payload, fetched.body, fetched.content_type, input_url)
        if fetched
        else (build_result(effective_payload, normalized), {"plain_text": "done"})
        if has_result
        else (None, {})
    )
    extraction = Extraction(
        user_id=user.id,
        type=payload.type,
        input_url=input_url,
        normalized_url=normalized,
        input_text=payload.text,
        detected_source_kind=kind,
        detected_domain=domain,
        detected_type=payload.type,
        status="succeeded" if has_result else "failed",
        result=parsed_result[0],
        error_code=fetch_error.code if fetch_error else None,
        error_message=str(fetch_error) if fetch_error else None,
        provider_trace={
            "fetch": "done" if fetched else "skipped",
            **parsed_result[1],
        },
        attempts=1,
        started_at=now,
        finished_at=now,
        expires_at=now + timedelta(days=30),
    )
    db.add(extraction)
    await db.commit()
    await db.refresh(extraction)
    result_response = response(extraction, duplicate)
    await save_response(
        db,
        user.id,
        idempotency_key,
        "POST",
        "/api/v1/extractions",
        request_payload,
        status.HTTP_202_ACCEPTED,
        result_response.model_dump(mode="json", by_alias=True),
    )
    await db.commit()
    return result_response


@router.get("/{extraction_id}", response_model=ExtractionResponse)
async def get_extraction(
    extraction_id: UUID, user: CurrentUser, db: DbSession
) -> ExtractionResponse:
    extraction = (
        await db.execute(
            select(Extraction).where(
                Extraction.id == extraction_id, Extraction.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if extraction is None:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return response(extraction)


@router.delete("/{extraction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_extraction(extraction_id: UUID, user: CurrentUser, db: DbSession) -> None:
    extraction = (
        await db.execute(
            select(Extraction).where(
                Extraction.id == extraction_id, Extraction.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if extraction is None:
        raise HTTPException(status_code=404, detail="Extraction not found")
    await db.delete(extraction)
    await db.commit()
