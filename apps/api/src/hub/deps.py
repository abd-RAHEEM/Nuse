import hashlib
import secrets
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub.db import get_db
from hub.models import Session, User

DbSession = Annotated[AsyncSession, Depends(get_db)]


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


async def current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get("hub_session")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated")

    result = await db.execute(
        select(Session, User)
        .join(User, User.id == Session.user_id)
        .where(
            Session.token_hash == hash_session_token(token),
            Session.revoked_at.is_(None),
            Session.expires_at > datetime.now(UTC),
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated")
    session = row[0]
    session.last_seen_at = datetime.now(UTC)
    await db.commit()
    return row[1]


CurrentUser = Annotated[User, Depends(current_user)]


def user_id(user: User) -> UUID:
    return user.id
