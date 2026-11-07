import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub.models import IdempotencyKey


def request_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def find_replay(
    db: AsyncSession,
    user_id: UUID,
    key: str | None,
    method: str,
    path: str,
    payload: Any,
    response: Response,
) -> dict | None:
    if not key:
        return None
    if len(key) > 200:
        raise HTTPException(status_code=422, detail="Invalid Idempotency-Key")
    current_hash = request_hash(payload)
    record = (
        await db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id,
                IdempotencyKey.key == key,
                IdempotencyKey.expires_at > datetime.now(UTC),
            )
        )
    ).scalar_one_or_none()
    if record is None:
        return None
    if record.method != method or record.path != path or record.request_hash != current_hash:
        raise HTTPException(status_code=422, detail="idempotency_conflict")
    response.headers["Idempotent-Replayed"] = "true"
    return record.response_body


async def save_response(
    db: AsyncSession,
    user_id: UUID,
    key: str | None,
    method: str,
    path: str,
    payload: Any,
    response_status: int,
    response_body: dict,
) -> None:
    if not key:
        return
    db.add(
        IdempotencyKey(
            user_id=user_id,
            key=key,
            method=method,
            path=path,
            request_hash=request_hash(payload),
            response_status=response_status,
            response_body=response_body,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
