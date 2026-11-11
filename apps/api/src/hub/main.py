import logging
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from hub.config import get_settings
from hub.db import build_session_factory
from hub.modules.auth.router import router as auth_router
from hub.modules.capture.router import router as capture_router
from hub.modules.dashboard.router import router as dashboard_router
from hub.modules.exports.router import router as exports_router
from hub.modules.integrations.gmail_router import router as gmail_integrations_router
from hub.modules.integrations.router import router as integrations_router
from hub.modules.jobs.router import router as jobs_router
from hub.modules.resources.router import router as resources_router
from hub.modules.settings.router import router as settings_router

logger = logging.getLogger(__name__)
PROBLEM_MEDIA_TYPE = "application/problem+json"

app = FastAPI(
    title="Nuse API",
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(resources_router)
app.include_router(settings_router)
app.include_router(exports_router)
app.include_router(dashboard_router)
app.include_router(capture_router)
app.include_router(gmail_integrations_router)
app.include_router(integrations_router)


def _problem_response(
    request: Request,
    status_code: int,
    code: str,
    title: str,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", uuid4().hex)
    content: dict[str, object] = {
        "type": f"https://nuse.local/errors/{code}",
        "title": title,
        "status": status_code,
        "code": code,
        "requestId": request_id,
    }
    if detail:
        content["detail"] = detail
    if errors:
        content["errors"] = errors
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=response_headers,
        media_type=PROBLEM_MEDIA_TYPE,
    )


def _http_error_code(status_code: int, detail: object) -> tuple[str, str]:
    text_detail = detail.strip().lower() if isinstance(detail, str) else ""
    known_codes = {
        "account temporarily locked": ("account_locked", "Account temporarily locked"),
        "invalid credentials": ("invalid_credentials", "Invalid credentials"),
        "signup is disabled": ("signup_disabled", "Signup is disabled"),
        "username is already taken": ("username_taken", "Username is already taken"),
        "idempotency_conflict": ("idempotency_conflict", "Idempotency key conflict"),
        "cannot move an application back to saved": (
            "invalid_transition",
            "Invalid status transition",
        ),
        "invalid_transition": ("invalid_transition", "Invalid status transition"),
    }
    if text_detail.startswith("unsafe_url:"):
        return "unsafe_url", "This URL cannot be fetched"
    if text_detail in known_codes:
        return known_codes[text_detail]
    if "needs reauthorization" in text_detail:
        return "integration_needs_reauth", "Integration needs reauthorization"
    if "not connected" in text_detail:
        return "integration_not_connected", "Integration is not connected"
    if "notion" in text_detail or "google calendar" in text_detail:
        return "integration_error", "Integration request failed"
    defaults = {
        400: ("validation_error", "Invalid request"),
        401: ("unauthenticated", "Authentication required"),
        403: ("forbidden", "Request is not allowed"),
        404: ("not_found", "Not found"),
        409: ("conflict", "Request conflicts with existing data"),
        422: ("validation_error", "Invalid request"),
        423: ("account_locked", "Account temporarily locked"),
        429: ("rate_limited", "Too many requests"),
        502: ("integration_error", "Integration request failed"),
        503: ("service_unavailable", "Service unavailable"),
    }
    code, title = defaults.get(
        status_code, ("internal_error", "Request failed")
    )
    return code, title


@app.middleware("http")
async def require_csrf_header(request: Request, call_next):
    request.state.request_id = uuid4().hex
    if (
        request.url.path.startswith("/api/v1/")
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.headers.get("X-Requested-With") != "hub"
    ):
        return _problem_response(
            request,
            status.HTTP_403_FORBIDDEN,
            "csrf_failed",
            "CSRF validation failed",
        )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code, title = _http_error_code(exc.status_code, exc.detail)
    detail = exc.detail if isinstance(exc.detail, str) else None
    if code == "invalid_credentials":
        detail = "The username or PIN is incorrect"
    return _problem_response(
        request,
        exc.status_code,
        code,
        title,
        detail,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"] if part != "body"),
            "message": error["msg"],
            "code": error["type"],
        }
        for error in exc.errors()
    ]
    return _problem_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation_error",
        "Invalid request",
        "One or more fields need attention",
        errors,
    )


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": get_settings().app_env}


@app.get("/health/ready", tags=["health"])
async def readiness() -> JSONResponse:
    session_factory = build_session_factory()
    if session_factory is None:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "database_not_configured"},
        )

    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "database_unavailable"},
        )
    return JSONResponse(status_code=200, content={"status": "ready"})


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
    logger.warning("Integration provider operation failed", exc_info=exc)
    return _problem_response(
        request,
        status.HTTP_502_BAD_GATEWAY,
        "integration_error",
        "Integration request failed",
        "The connected service could not complete the request",
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> Response:
    logger.exception("Unhandled API error", exc_info=exc)
    return _problem_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "Internal server error",
        "The request could not be completed",
    )
