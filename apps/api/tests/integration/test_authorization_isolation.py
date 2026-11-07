import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from hub.config import get_settings
from hub.db import build_session_factory
from hub.main import app
from hub.models import CollectionResource, ResourceTag, Tag, User
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
