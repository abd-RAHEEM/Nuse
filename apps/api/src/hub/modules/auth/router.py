import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from hub.config import get_settings
from hub.deps import CurrentUser, DbSession, hash_session_token, new_session_token
from hub.models import LoginAttempt, Session, User
from hub.modules.auth.schemas import (
    AuthRequest,
    AuthResponse,
    ChangePinRequest,
    UserResponse,
)
from hub.modules.auth.security import hash_pin, verify_pin

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
SESSION_COOKIE = "hub_session"
SESSION_DAYS = 30
LOCKOUT_FAILURES = 5
LOCKOUT_WINDOW = timedelta(minutes=15)
LOCKOUT_DURATION = timedelta(minutes=15)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=get_settings().app_env != "development",
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )


async def _create_session(db: DbSession, user: User, request: Request) -> str:
    token = new_session_token()
    now = datetime.now(UTC)
    db.add(
        Session(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=now + timedelta(days=SESSION_DAYS),
            user_agent=request.headers.get("user-agent"),
            ip_hash=hashlib.sha256(
                (request.client.host if request.client else "unknown").encode()
            ).hexdigest(),
        )
    )
    user.last_login_at = now
    await db.commit()
    return token


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _record_attempt(
    db: DbSession, username: str, request: Request, succeeded: bool
) -> None:
    db.add(
        LoginAttempt(
            username_lower=username,
            ip=_client_ip(request),
            succeeded=succeeded,
        )
    )
    await db.flush()


async def _is_locked(db: DbSession, username: str, request: Request) -> bool:
    since = datetime.now(UTC) - LOCKOUT_WINDOW
    result = await db.execute(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.username_lower == username,
            LoginAttempt.ip == _client_ip(request),
            LoginAttempt.succeeded.is_(False),
            LoginAttempt.created_at >= since,
        )
    )
    return (result.scalar_one() or 0) >= LOCKOUT_FAILURES


def _locked_response() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_423_LOCKED,
        detail="Account temporarily locked",
        headers={"Retry-After": str(int(LOCKOUT_DURATION.total_seconds()))},
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: AuthRequest, request: Request, response: Response, db: DbSession
) -> AuthResponse:
    if not get_settings().allow_signup:
        raise HTTPException(status_code=403, detail="Signup is disabled")
    user = User(
        username=payload.username,
        pin_hash=hash_pin(payload.pin),
        display_name=payload.display_name.strip() if payload.display_name else None,
    )
    db.add(user)
    try:
        await db.flush()
        token = await _create_session(db, user, request)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Username is already taken") from None
    _set_session_cookie(response, token)
    return AuthResponse(user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: AuthRequest, request: Request, response: Response, db: DbSession
) -> AuthResponse:
    if await _is_locked(db, payload.username, request):
        raise _locked_response()
    result = await db.execute(select(User).where(User.username == payload.username))
    user = result.scalar_one_or_none()
    valid = verify_pin(payload.pin, user.pin_hash if user else None)
    if user is None or not valid:
        await _record_attempt(db, payload.username, request, succeeded=False)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    await _record_attempt(db, payload.username, request, succeeded=True)
    token = await _create_session(db, user, request)
    _set_session_cookie(response, token)
    return AuthResponse(user=UserResponse.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: DbSession) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        result = await db.execute(
            select(Session).where(Session.token_hash == hash_session_token(token))
        )
        session = result.scalar_one_or_none()
        if session:
            session.revoked_at = datetime.now(UTC)
            await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: CurrentUser, response: Response, db: DbSession) -> None:
    await db.execute(
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/change-pin", status_code=status.HTTP_204_NO_CONTENT)
async def change_pin(
    payload: ChangePinRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbSession,
) -> None:
    if not verify_pin(payload.current_pin, user.pin_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if payload.current_pin == payload.new_pin:
        raise HTTPException(status_code=422, detail="New PIN must be different")

    user.pin_hash = hash_pin(payload.new_pin)
    current_token = request.cookies.get(SESSION_COOKIE)
    await db.execute(
        update(Session)
        .where(
            Session.user_id == user.id,
            Session.revoked_at.is_(None),
            Session.token_hash != (
                hash_session_token(current_token) if current_token else ""
            ),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
