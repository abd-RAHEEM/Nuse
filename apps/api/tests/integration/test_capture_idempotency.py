import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from hub.config import get_settings
from hub.db import build_session_factory
from hub.main import app
from hub.models import User
from hub.modules.auth.security import hash_pin

pytestmark = pytest.mark.integration


def _headers() -> dict[str, str]:
    return {"X-Requested-With": "hub"}


def _client() -> TestClient:
    return TestClient(app)


def _cleanup(user_id: str) -> None:
    async def delete_user() -> None:
        factory = build_session_factory()
        assert factory is not None
        async with factory() as db:
            user = await db.scalar(select(User).where(User.id == user_id))
            if user:
                await db.delete(user)
                await db.commit()

    asyncio.run(delete_user())


@pytest.mark.skipif(
    not get_settings().database_url,
    reason="DATABASE_URL is required for database-backed idempotency tests",
)
def test_extraction_idempotency_replays_and_rejects_changed_body() -> None:
    client = _client()
    user_id = ""
    try:
        username = f"idem_{uuid4().hex[:12]}"

        async def create_user() -> str:
            factory = build_session_factory()
            assert factory is not None
            async with factory() as db:
                user = User(username=username, pin_hash=hash_pin("135790"))
                db.add(user)
                await db.commit()
                return str(user.id)

        user_id = asyncio.run(create_user())
        login = client.post(
            "/api/v1/auth/login",
            headers=_headers(),
            json={"username": username, "pin": "135790"},
        )
        assert login.status_code == 200, login.text
        headers = {**_headers(), "Idempotency-Key": str(uuid4())}
        payload = {"type": "resource", "text": "A useful article"}

        first = client.post("/api/v1/extractions", headers=headers, json=payload)
        replay = client.post("/api/v1/extractions", headers=headers, json=payload)
        conflict = client.post(
            "/api/v1/extractions",
            headers=headers,
            json={"type": "resource", "text": "A different article"},
        )

        assert first.status_code == 202, first.text
        assert replay.status_code == 202, replay.text
        assert replay.headers["Idempotent-Replayed"] == "true"
        assert replay.json()["id"] == first.json()["id"]
        assert conflict.status_code == 422
        assert conflict.json()["detail"] == "idempotency_conflict"
    finally:
        if user_id:
            _cleanup(user_id)
        client.close()
