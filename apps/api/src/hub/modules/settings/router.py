from fastapi import APIRouter

from hub.deps import CurrentUser, DbSession
from hub.modules.settings.schemas import SettingsResponse, UpdateSettingsRequest

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings(user: CurrentUser) -> SettingsResponse:
    return SettingsResponse(display_name=user.display_name, timezone=user.timezone)


@router.patch("", response_model=SettingsResponse)
async def update_settings(
    payload: UpdateSettingsRequest, user: CurrentUser, db: DbSession
) -> SettingsResponse:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return SettingsResponse(display_name=user.display_name, timezone=user.timezone)
