import asyncio
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from hub.config import get_settings
from hub.db import build_session_factory
from hub.main import app
from hub.models import CollectionResource, JobEvent, ResourceTag, Tag, User
from hub.modules.auth.security import hash_pin

pytestmark = pytest.mark.integration


def _client() -> TestClient:
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"X-Requested-With": "hub"}


def _create_user(client: TestClient, username: str) -> str:
    async def create() -> str:
        factory = build_session_factory()
        assert factory is not None
        async with factory() as db:
            user = User(username=username, pin_hash=hash_pin("135790"))
            db.add(user)
            await db.commit()
            return str(user.id)

    user_id = asyncio.run(create())
    response = client.post(
        "/api/v1/auth/login",
        headers=_headers(),
        json={"username": username, "pin": "135790"},
    )
    assert response.status_code == 200, response.text
    return user_id


async def _cleanup_user(user_id: str) -> None:
    factory = build_session_factory()
    assert factory is not None
    async with factory() as db:
        user = await db.scalar(select(User).where(User.id == user_id))
        if user is not None:
            await db.delete(user)
            await db.commit()


def _cleanup(user_ids: list[str]) -> None:
    for user_id in user_ids:
        asyncio.run(_cleanup_user(user_id))


@pytest.fixture
def two_users() -> tuple[TestClient, TestClient, str, str, list[str], list[str]]:
    first_client = _client()
    second_client = _client()
    user_ids: list[str] = []
    usernames: list[str] = []
    try:
        usernames.extend([f"iso_{uuid4().hex[:12]}", f"iso_{uuid4().hex[:12]}"])
        user_ids.append(_create_user(first_client, usernames[0]))
        user_ids.append(_create_user(second_client, usernames[1]))
        yield first_client, second_client, user_ids[0], user_ids[1], user_ids, usernames
    finally:
        _cleanup(user_ids)
        first_client.close()
        second_client.close()


@pytest.mark.skipif(
    not get_settings().database_url,
    reason="DATABASE_URL is required for database-backed signup tests",
)
def test_signup_remains_available_when_users_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    from hub.modules import auth

    settings = get_settings().model_copy(update={"allow_signup": True})
    monkeypatch.setattr(auth.router, "get_settings", lambda: settings)
    client = _client()
    user_ids: list[str] = []
    try:
        for _ in range(2):
            response = client.post(
                "/api/v1/auth/signup",
                headers=_headers(),
                json={
                    "username": f"signup_{uuid4().hex[:12]}",
                    "pin": "135790",
                },
            )
            assert response.status_code == 201, response.text
            user_ids.append(response.json()["user"]["id"])
    finally:
        _cleanup(user_ids)
        client.close()


@pytest.mark.skipif(
    not get_settings().database_url,
    reason="DATABASE_URL is required for database-backed isolation tests",
)
def test_jobs_are_isolated_between_users(
    two_users: tuple[TestClient, TestClient, str, str, list[str], list[str]],
) -> None:
    first_client, second_client, _, second_user_id, _, _ = two_users
    first_job = first_client.post(
        "/api/v1/jobs",
        headers=_headers(),
        json={
            "intent": "applied",
            "company": "Isolation Systems",
            "title": "Private platform role",
            "sourceUrl": "https://example.com/private-job",
        },
    )
    assert first_job.status_code == 201, first_job.text
    job_id = first_job.json()["id"]
    assert second_client.get(f"/api/v1/jobs/{job_id}").status_code == 404
    assert second_client.patch(
        f"/api/v1/jobs/{job_id}",
        headers=_headers(),
        json={"title": "Cross-user edit"},
    ).status_code == 404
    assert second_client.delete(
        f"/api/v1/jobs/{job_id}", headers=_headers()
    ).status_code == 404
    assert second_user_id


@pytest.mark.skipif(
    not get_settings().database_url,
    reason="DATABASE_URL is required for database-backed job filter tests",
)
def test_job_filters_and_keyset_pagination(
    two_users: tuple[TestClient, TestClient, str, str, list[str], list[str]],
) -> None:
    client, _, _, _, _, _ = two_users
    records = [
        {
            "intent": "applied",
            "company": "Filter Systems",
            "title": "Remote platform role",
            "location": "Singapore",
            "workMode": "remote",
            "appliedOn": "2026-11-02",
            "nextFollowUpOn": "2026-11-12",
        },
        {
            "intent": "applied",
            "company": "Filter Systems",
            "title": "Office data role",
            "location": "Pune",
            "workMode": "onsite",
            "appliedOn": "2026-11-05",
            "nextFollowUpOn": "2026-11-15",
        },
        {
            "intent": "saved",
            "company": "Different Works",
            "title": "Saved design role",
            "location": "Remote",
        },
    ]
    created = [
        client.post("/api/v1/jobs", headers=_headers(), json=record)
        for record in records
    ]
    assert all(response.status_code == 201 for response in created)

    filtered = client.get(
        "/api/v1/jobs",
        params=[
            ("company", "Filter"),
            ("status[]", "applied"),
            ("location", "Remote"),
            ("appliedFrom", "2026-11-01"),
            ("appliedTo", "2026-11-10"),
            ("followUpBefore", "2026-11-13"),
            ("sort", "next_action"),
        ],
    )
    assert filtered.status_code == 200
    assert [item["title"] for item in filtered.json()["items"]] == [
        "Remote platform role"
    ]

    first_page = client.get(
        "/api/v1/jobs",
        params={"company": "Filter", "limit": 1, "sort": "newest"},
    )
    assert first_page.status_code == 200
    cursor = first_page.json()["nextCursor"]
    assert cursor
    second_page = client.get(
        "/api/v1/jobs",
        params={"company": "Filter", "limit": 1, "sort": "newest", "cursor": cursor},
    )
    assert second_page.status_code == 200
    assert second_page.json()["items"][0]["id"] != first_page.json()["items"][0]["id"]

    invalid_cursor = client.get(
        "/api/v1/jobs", params={"cursor": "not-a-cursor"}
    )
    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["code"] == "validation_error"


@pytest.mark.skipif(
    not get_settings().database_url,
    reason="DATABASE_URL is required for database-backed status tests",
)
def test_job_status_updates_write_timeline_events(
    two_users: tuple[TestClient, TestClient, str, str, list[str], list[str]],
) -> None:
    client, _, _, _, _, _ = two_users
    created = client.post(
        "/api/v1/jobs",
        headers=_headers(),
        json={"intent": "saved", "company": "Timeline Systems", "title": "QA role"},
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    applied = client.patch(
        f"/api/v1/jobs/{job_id}",
        headers=_headers(),
        json={"status": "applied"},
    )
    assert applied.status_code == 200, applied.text
    applied_body = applied.json()
    assert applied_body["appliedOn"] == datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).date().isoformat()
    assert [event["type"] for event in applied_body["timeline"]] == ["saved", "applied"]
    assert applied_body["timeline"][-1]["title"] == "Job applied"

    async def applied_event_has_application() -> bool:
        factory = build_session_factory()
        assert factory is not None
        async with factory() as db:
            event = await db.scalar(
                select(JobEvent).where(
                    JobEvent.job_id == UUID(job_id),
                    JobEvent.type == "applied",
                )
            )
            return event is not None and event.application_id is not None

    assert asyncio.run(applied_event_has_application())

    interviewed = client.patch(
        f"/api/v1/jobs/{job_id}",
        headers=_headers(),
        json={"status": "interview"},
    )
    assert interviewed.status_code == 200, interviewed.text
    timeline = interviewed.json()["timeline"]
    assert [event["type"] for event in timeline] == ["saved", "applied", "status_changed"]
    assert timeline[-1]["title"] == "Status changed to Interview"

    unchanged = client.patch(
        f"/api/v1/jobs/{job_id}",
        headers=_headers(),
        json={"status": "interview"},
    )
    assert unchanged.status_code == 200, unchanged.text
    assert len(unchanged.json()["timeline"]) == 3


@pytest.mark.skipif(
    not get_settings().database_url,
    reason="DATABASE_URL is required for settings and export tests",
)
def test_settings_and_exports_are_user_scoped(
    two_users: tuple[TestClient, TestClient, str, str, list[str], list[str]],
) -> None:
    client, other_client, _, _, _, _ = two_users
    settings_response = client.patch(
        "/api/v1/settings",
        headers=_headers(),
        json={"displayName": "  Local QA  ", "timezone": "Asia/Singapore"},
    )
    assert settings_response.status_code == 200, settings_response.text
    assert settings_response.json() == {
        "displayName": "Local QA",
        "timezone": "Asia/Singapore",
    }
    assert client.get("/api/v1/settings").json()["displayName"] == "Local QA"

    invalid_timezone = client.patch(
        "/api/v1/settings",
        headers=_headers(),
        json={"timezone": "Not/A_Real_Zone"},
    )
    assert invalid_timezone.status_code == 422
    assert invalid_timezone.json()["code"] == "validation_error"

    job = client.post(
        "/api/v1/jobs",
        headers=_headers(),
        json={
            "intent": "applied",
            "company": "Export Systems",
            "title": "Export test role",
            "appliedOn": "2026-11-02",
        },
    )
    resource = client.post(
        "/api/v1/resources",
        headers=_headers(),
        json={
            "title": "Export test resource",
            "category": "article",
            "description": "A test entry",
        },
    )
    assert job.status_code == 201
    assert resource.status_code == 201

    job_export = client.get("/api/v1/exports/jobs?format=json")
    resource_export = client.get("/api/v1/exports/resources?format=json")
    assert job_export.status_code == 200
    assert job_export.headers["content-disposition"].endswith(
        'filename="nuse-jobs.json"'
    )
    assert job_export.json()[0]["timeline"]
    assert resource_export.json()[0]["title"] == "Export test resource"
    assert other_client.get("/api/v1/exports/jobs?format=json").json() == []
    empty_export = other_client.get("/api/v1/exports/resources?format=csv")
    assert empty_export.status_code == 200
    assert empty_export.text.startswith("id,title,category,sourceUrl")


@pytest.mark.skipif(
    not get_settings().database_url,
    reason="DATABASE_URL is required for database-backed isolation tests",
)
def test_resources_tags_and_collections_are_isolated(
    two_users: tuple[TestClient, TestClient, str, str, list[str], list[str]],
) -> None:
    first_client, second_client, first_user_id, second_user_id, _, _ = two_users
    first_resource = first_client.post(
        "/api/v1/resources",
        headers=_headers(),
        json={
            "title": "Private resource",
            "category": "article",
            "sourceUrl": "https://example.com/private-resource",
        },
    )
    assert first_resource.status_code == 201, first_resource.text
    resource_id = first_resource.json()["id"]
    first_collection = first_client.post(
        "/api/v1/collections",
        headers=_headers(),
        json={"name": "Private collection"},
    )
    assert first_collection.status_code == 201, first_collection.text
    collection_id = first_collection.json()["id"]

    factory = build_session_factory()
    assert factory is not None

    async def seed_tag() -> str:
        async with factory() as db:
            tag = Tag(
                user_id=first_user_id,
                name="Private",
                slug=f"private-{uuid4().hex[:8]}",
            )
            db.add(tag)
            await db.flush()
            db.add(ResourceTag(resource_id=resource_id, tag_id=tag.id))
            db.add(CollectionResource(collection_id=collection_id, resource_id=resource_id))
            await db.commit()
            return str(tag.id)

    tag_id = asyncio.run(seed_tag())
    first_detail = first_client.get(f"/api/v1/resources/{resource_id}")
    assert first_detail.status_code == 200
    assert first_detail.json()["tags"][0]["id"] == tag_id
    assert first_detail.json()["collectionIds"] == [collection_id]
    first_collections = first_client.get("/api/v1/collections")
    assert first_collections.status_code == 200
    assert first_collections.json()["items"][0]["resourceCount"] == 1
    first_tags = first_client.get("/api/v1/tags")
    assert first_tags.status_code == 200
    assert first_tags.json()["items"][0]["resourceCount"] == 1

    assert second_client.get(f"/api/v1/resources/{resource_id}").status_code == 404
    assert second_client.get("/api/v1/resources").json()["items"] == []
    assert second_client.get("/api/v1/tags").json()["items"] == []
    assert second_client.get("/api/v1/collections").json()["items"] == []
    assert second_client.patch(
        f"/api/v1/resources/{resource_id}",
        headers=_headers(),
        json={"title": "Cross-user edit"},
    ).status_code == 404
    assert second_client.delete(
        f"/api/v1/resources/{resource_id}", headers=_headers()
    ).status_code == 404
    assert second_client.patch(
        f"/api/v1/tags/{tag_id}",
        headers=_headers(),
        json={"name": "Cross-user tag"},
    ).status_code == 404
    assert second_client.delete(f"/api/v1/tags/{tag_id}", headers=_headers()).status_code == 404
    assert second_client.patch(
        f"/api/v1/collections/{collection_id}",
        headers=_headers(),
        json={"name": "Cross-user collection"},
    ).status_code == 404
    assert second_client.delete(
        f"/api/v1/collections/{collection_id}", headers=_headers()
    ).status_code == 404
    assert second_user_id
