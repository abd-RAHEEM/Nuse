from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select

from hub.common.idempotency import find_replay, save_response
from hub.deps import CurrentUser, DbSession
from hub.models import (
    Collection,
    CollectionResource,
    Extraction,
    JobTag,
    Resource,
    ResourceDetail,
    ResourceTag,
    Tag,
)
from hub.modules.resources.schemas import (
    CollectionListResponse,
    CollectionResponse,
    CreateCollectionRequest,
    CreateResourceRequest,
    RenameTagRequest,
    ResourceDetailResponse,
    ResourcePageResponse,
    ResourceSummaryResponse,
    TagListResponse,
    TagResponse,
    UpdateCollectionRequest,
    UpdateResourceRequest,
)

router = APIRouter(prefix="/api/v1", tags=["resources"])


async def _resource(db: DbSession, resource: Resource) -> ResourceDetailResponse:
    details = (
        await db.execute(select(ResourceDetail).where(ResourceDetail.resource_id == resource.id))
    ).scalar_one_or_none()
    tags = (
        await db.execute(
            select(Tag)
            .join(ResourceTag, ResourceTag.tag_id == Tag.id)
            .where(ResourceTag.resource_id == resource.id, Tag.user_id == resource.user_id)
        )
    ).scalars()
    collection_ids = (
        await db.execute(
            select(CollectionResource.collection_id).where(
                CollectionResource.resource_id == resource.id
            )
        )
    ).scalars()
    return ResourceDetailResponse(
        **ResourceSummaryResponse.model_validate(resource).model_dump(
            exclude={"tags", "collection_ids"}
        ),
        tags=[{"id": str(tag.id), "name": tag.name} for tag in tags],
        collection_ids=list(collection_ids),
        summary=resource.summary,
        notes=resource.notes,
        details=details.data if details else None,
        verification_note=resource.verification_note,
        updated_at=resource.updated_at,
    )


async def _find_resource(db: DbSession, user_id: UUID, resource_id: UUID) -> Resource:
    resource = (
        await db.execute(
            select(Resource).where(Resource.id == resource_id, Resource.user_id == user_id)
        )
    ).scalar_one_or_none()
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


@router.get("/resources", response_model=ResourcePageResponse)
async def list_resources(
    user: CurrentUser,
    db: DbSession,
    q: str | None = None,
    category: str | None = None,
    favorite: bool | None = None,
    saved_for_later: bool | None = None,
    limit: int = Query(default=25, ge=1, le=100),
) -> ResourcePageResponse:
    query = (
        select(Resource)
        .where(Resource.user_id == user.id)
        .order_by(Resource.created_at.desc())
        .limit(limit)
    )
    if q:
        query = query.where(Resource.title.ilike(f"%{q}%"))
    if category:
        query = query.where(Resource.category == category)
    if favorite is not None:
        query = query.where(Resource.is_favorite == favorite)
    if saved_for_later is not None:
        query = query.where(Resource.is_saved_for_later == saved_for_later)
    resources = (await db.execute(query)).scalars()
    return ResourcePageResponse(
        items=[
            await _resource_summary(db, resource)
            for resource in resources
        ],
        next_cursor=None,
    )


async def _resource_summary(db: DbSession, resource: Resource) -> ResourceSummaryResponse:
    tags = (
        await db.execute(
            select(Tag)
            .join(ResourceTag, ResourceTag.tag_id == Tag.id)
            .where(ResourceTag.resource_id == resource.id, Tag.user_id == resource.user_id)
        )
    ).scalars()
    collection_ids = (
        await db.execute(
            select(CollectionResource.collection_id).where(
                CollectionResource.resource_id == resource.id
            )
        )
    ).scalars()
    return ResourceSummaryResponse(
        **ResourceSummaryResponse.model_validate(resource).model_dump(
            exclude={"tags", "collection_ids"}
        ),
        tags=[{"id": str(tag.id), "name": tag.name} for tag in tags],
        collection_ids=list(collection_ids),
    )


@router.post(
    "/resources",
    response_model=ResourceDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_resource(
    payload: CreateResourceRequest,
    user: CurrentUser,
    db: DbSession,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ResourceDetailResponse:
    request_payload = payload.model_dump(mode="json")
    replay = await find_replay(
        db,
        user.id,
        idempotency_key,
        "POST",
        "/api/v1/resources",
        request_payload,
        response,
    )
    if replay is not None:
        return ResourceDetailResponse.model_validate(replay)
    resource = Resource(
        user_id=user.id,
        title=payload.title,
        category=payload.category,
        source_url=payload.source_url,
        source_platform=payload.source_platform,
        description=payload.description,
        summary=payload.summary,
        notes=payload.notes,
        is_favorite=payload.is_favorite,
        is_saved_for_later=payload.is_saved_for_later,
        extraction_id=payload.extraction_id,
        field_provenance=payload.field_provenance,
    )
    db.add(resource)
    await db.flush()
    if payload.details is not None:
        db.add(ResourceDetail(resource_id=resource.id, data=payload.details))
    if payload.extraction_id:
        extraction = (
            await db.execute(
                select(Extraction).where(
                    Extraction.id == payload.extraction_id,
                    Extraction.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if extraction is not None:
            extraction.status = "consumed"
    await db.commit()
    await db.refresh(resource)
    detail = await _resource(db, resource)
    await save_response(
        db,
        user.id,
        idempotency_key,
        "POST",
        "/api/v1/resources",
        request_payload,
        status.HTTP_201_CREATED,
        detail.model_dump(mode="json", by_alias=True),
    )
    await db.commit()
    return detail


@router.get("/resources/{resource_id}", response_model=ResourceDetailResponse)
async def get_resource(
    resource_id: UUID, user: CurrentUser, db: DbSession
) -> ResourceDetailResponse:
    return await _resource(db, await _find_resource(db, user.id, resource_id))


@router.patch("/resources/{resource_id}", response_model=ResourceDetailResponse)
async def update_resource(
    resource_id: UUID, payload: UpdateResourceRequest, user: CurrentUser, db: DbSession
) -> ResourceDetailResponse:
    resource = await _find_resource(db, user.id, resource_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(resource, field, value)
    await db.commit()
    await db.refresh(resource)
    return await _resource(db, resource)


@router.delete("/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(resource_id: UUID, user: CurrentUser, db: DbSession) -> None:
    resource = await _find_resource(db, user.id, resource_id)
    await db.delete(resource)
    await db.commit()


@router.get("/tags", response_model=TagListResponse)
async def list_tags(
    user: CurrentUser, db: DbSession, q: str | None = None, limit: int = Query(default=50, le=100)
) -> TagListResponse:
    query = select(Tag).where(Tag.user_id == user.id).order_by(Tag.name).limit(limit)
    if q:
        query = query.where(Tag.name.ilike(f"%{q}%"))
    tags = (await db.execute(query)).scalars()
    items = []
    for tag in tags:
        job_count = await db.scalar(
            select(func.count(JobTag.job_id)).where(JobTag.tag_id == tag.id)
        )
        resource_count = await db.scalar(
            select(func.count(ResourceTag.resource_id)).where(ResourceTag.tag_id == tag.id)
        )
        items.append(
            TagResponse(
                id=tag.id,
                name=tag.name,
                job_count=job_count or 0,
                resource_count=resource_count or 0,
            )
        )
    return TagListResponse(items=items)


@router.patch("/tags/{tag_id}", response_model=TagResponse)
async def rename_tag(
    tag_id: UUID, payload: RenameTagRequest, user: CurrentUser, db: DbSession
) -> TagResponse:
    tag = (
        await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
    ).scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    tag.name = payload.name
    tag.slug = payload.name.strip().lower().replace(" ", "-")
    await db.commit()
    return TagResponse.model_validate(tag)


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: UUID, user: CurrentUser, db: DbSession) -> None:
    tag = (
        await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
    ).scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.commit()


@router.get("/collections", response_model=CollectionListResponse)
async def list_collections(user: CurrentUser, db: DbSession) -> CollectionListResponse:
    collections = (
        await db.execute(
            select(Collection)
            .where(Collection.user_id == user.id)
            .order_by(Collection.name)
        )
    ).scalars()
    items = []
    for collection in collections:
        count = await db.scalar(
            select(func.count(CollectionResource.resource_id)).where(
                CollectionResource.collection_id == collection.id
            )
        )
        items.append(
            CollectionResponse(
                id=collection.id,
                name=collection.name,
                description=collection.description,
                resource_count=count or 0,
            )
        )
    return CollectionListResponse(items=items)


@router.post("/collections", response_model=CollectionResponse, status_code=201)
async def create_collection(
    payload: CreateCollectionRequest, user: CurrentUser, db: DbSession
) -> CollectionResponse:
    collection = Collection(user_id=user.id, name=payload.name, description=payload.description)
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return CollectionResponse.model_validate(collection)


@router.patch("/collections/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: UUID, payload: UpdateCollectionRequest, user: CurrentUser, db: DbSession
) -> CollectionResponse:
    collection = (
        await db.execute(
            select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
        )
    ).scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(collection, field, value)
    await db.commit()
    return CollectionResponse.model_validate(collection)


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(collection_id: UUID, user: CurrentUser, db: DbSession) -> None:
    collection = (
        await db.execute(
            select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
        )
    ).scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    await db.delete(collection)
    await db.commit()


@router.put(
    "/collections/{collection_id}/resources/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def add_to_collection(
    collection_id: UUID, resource_id: UUID, user: CurrentUser, db: DbSession
) -> None:
    collection = (
        await db.execute(
            select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
        )
    ).scalar_one_or_none()
    resource = await _find_resource(db, user.id, resource_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    existing = await db.execute(
        select(CollectionResource).where(
            CollectionResource.collection_id == collection.id,
            CollectionResource.resource_id == resource.id,
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(CollectionResource(collection_id=collection.id, resource_id=resource.id))
        await db.commit()


@router.delete(
    "/collections/{collection_id}/resources/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_from_collection(
    collection_id: UUID, resource_id: UUID, user: CurrentUser, db: DbSession
) -> None:
    collection = (
        await db.execute(
            select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
        )
    ).scalar_one_or_none()
    resource = await _find_resource(db, user.id, resource_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    await db.execute(
        delete(CollectionResource).where(
            CollectionResource.collection_id == collection.id,
            CollectionResource.resource_id == resource.id,
        )
    )
    await db.commit()
