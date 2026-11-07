from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from hub.config import get_settings
from hub.db import build_session_factory
from hub.modules.auth.router import router as auth_router
from hub.modules.capture.router import router as capture_router
from hub.modules.dashboard.router import router as dashboard_router
from hub.modules.integrations.router import router as integrations_router
from hub.modules.jobs.router import router as jobs_router
from hub.modules.resources.router import router as resources_router

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
app.include_router(dashboard_router)
app.include_router(capture_router)
app.include_router(integrations_router)


@app.middleware("http")
async def require_csrf_header(request: Request, call_next):
    if (
        request.url.path.startswith("/api/v1/")
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.headers.get("X-Requested-With") != "hub"
    ):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "type": "https://nuse.local/errors/csrf_failed",
                "title": "CSRF validation failed",
                "status": 403,
                "code": "csrf_failed",
            },
        )
    return await call_next(request)


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
async def runtime_error_handler(_: Request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "type": "https://nuse.local/errors/service_unavailable",
            "title": "Service unavailable",
            "status": 503,
            "code": "service_unavailable",
            "detail": str(exc),
        },
    )
