from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from hub.modules.integrations.router import (
    _ensure_notion_tag_options,
    _google_event_body,
    _notion_blocks,
    _notion_category_label,
    _notion_database_items,
    _sync_notion_blocks,
)
from hub.modules.integrations.schemas import CalendarEventRequest


def test_notion_database_items_maps_data_sources() -> None:
    items = _notion_database_items(
        [
            {
                "object": "data_source",
                "id": "source-id",
                "title": [{"plain_text": "Career resources"}],
            },
            {"object": "page", "id": "page-id", "title": []},
            {"object": "data_source", "id": "untitled-id"},
        ]
    )

    assert items == [
        {"id": "source-id", "title": "Career resources"},
        {"id": "untitled-id", "title": "Untitled database"},
    ]


def test_notion_resource_categories_match_database_option_labels() -> None:
    assert _notion_category_label("ai_tool") == "AI Tools"
    assert _notion_category_label("developer_resource") == "Developer Resources"
    assert _notion_category_label("other") == "Other"


@pytest.mark.asyncio
async def test_notion_export_adds_only_missing_multi_select_tag_options() -> None:
    client = SimpleNamespace(
        get=AsyncMock(
            return_value=Mock(
                status_code=200,
                json=Mock(
                    return_value={
                        "properties": {
                            "Tags": {
                                "type": "multi_select",
                                "multi_select": {
                                    "options": [{"id": "python-id", "name": "Python"}]
                                },
                            }
                        }
                    }
                ),
            )
        ),
        patch=AsyncMock(return_value=Mock(status_code=200)),
    )

    await _ensure_notion_tag_options(client, "secret", "source-id", ["Python", "AI tooling"])

    client.patch.assert_awaited_once()
    assert client.patch.await_args.kwargs["json"] == {
        "properties": {
            "Tags": {
                "multi_select": {
                    "options": [{"id": "python-id"}, {"name": "AI tooling"}]
                }
            }
        }
    }


def test_standalone_calendar_event_accepts_popup_reminder() -> None:
    event = CalendarEventRequest.model_validate(
        {
            "title": "Project interview",
            "startsAt": "2026-11-12T10:00:00+08:00",
            "timeZone": "Asia/Singapore",
            "reminders": [{"method": "popup", "minutes": 10}],
        }
    )

    assert event.job_id is None
    assert event.reminders[0].minutes == 10


def test_calendar_timeline_event_requires_job_context() -> None:
    with pytest.raises(ValueError, match="must belong to a job"):
        CalendarEventRequest.model_validate(
            {
                "jobEventId": "59d82676-061a-4f4b-a701-a8f72f8457ab",
                "title": "Interview",
                "startsAt": "2026-11-12T10:00:00+08:00",
            }
        )


def test_google_event_body_contains_popup_reminder_and_selected_details() -> None:
    event = CalendarEventRequest.model_validate(
        {
            "title": "Design interview",
            "description": "Bring a portfolio",
            "location": "Video call",
            "startsAt": "2026-11-12T10:00:00+08:00",
            "endsAt": "2026-11-12T11:00:00+08:00",
            "timeZone": "Asia/Singapore",
            "reminders": [{"method": "popup", "minutes": 15}],
        }
    )

    body = _google_event_body(event, None)

    assert body["summary"] == "Design interview"
    assert body["location"] == "Video call"
    assert body["reminders"] == {
        "useDefault": False,
        "overrides": [{"method": "popup", "minutes": 15}],
    }
    assert body["start"] == {
        "dateTime": "2026-11-12T10:00:00+08:00",
        "timeZone": "Asia/Singapore",
    }
    assert body["end"] == {
        "dateTime": "2026-11-12T11:00:00+08:00",
        "timeZone": "Asia/Singapore",
    }


def test_google_all_day_body_uses_exclusive_end_date() -> None:
    event = CalendarEventRequest.model_validate(
        {
            "title": "Conference",
            "startsAt": "2026-11-12T00:00:00+00:00",
            "endsAt": "2026-11-13T00:00:00+00:00",
            "allDay": True,
            "timeZone": "Asia/Singapore",
        }
    )

    body = _google_event_body(event, None)

    assert body["start"] == {"date": "2026-11-12"}
    assert body["end"] == {"date": "2026-11-14"}


def test_notion_blocks_split_long_text_at_rich_text_limit() -> None:
    resource = SimpleNamespace(description="a" * 2001, summary=None, notes=None)

    blocks = _notion_blocks(resource)

    contents = [
        block["paragraph"]["rich_text"][0]["text"]["content"]
        for block in blocks
    ]
    assert [len(content) for content in contents] == [1900, 101]
    assert "".join(contents) == "a" * 2001


@pytest.mark.asyncio
async def test_sync_notion_blocks_updates_and_adds_owned_blocks() -> None:
    client = SimpleNamespace(
        patch=AsyncMock(
            side_effect=[
                Mock(status_code=200),
                Mock(status_code=200, json=Mock(return_value={"results": [{"id": "new"}]})),
            ]
        ),
    )
    blocks = [
        {"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "first"}}]}},
        {"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "second"}}]}},
    ]

    result = await _sync_notion_blocks(client, "token", "page", blocks, ["owned"])

    assert result == ["owned", "new"]
    assert client.patch.await_count == 2


@pytest.mark.asyncio
async def test_sync_notion_blocks_removes_outdated_owned_blocks() -> None:
    client = SimpleNamespace(
        patch=AsyncMock(return_value=Mock(status_code=200)),
        delete=AsyncMock(return_value=Mock(status_code=200)),
    )
    blocks = [{"type": "paragraph", "paragraph": {"rich_text": []}}]

    result = await _sync_notion_blocks(
        client,
        "token",
        "page",
        blocks,
        ["owned", "outdated"],
    )

    assert result == ["owned"]
    client.delete.assert_awaited_once()
    assert client.delete.await_args.args[0].endswith("/blocks/outdated")


@pytest.mark.asyncio
async def test_sync_notion_blocks_surfaces_provider_errors() -> None:
    client = SimpleNamespace(patch=AsyncMock(return_value=Mock(status_code=500)))
    blocks = [{"type": "paragraph", "paragraph": {"rich_text": []}}]

    with pytest.raises(RuntimeError, match="could not update"):
        await _sync_notion_blocks(client, "token", "page", blocks, ["owned"])
