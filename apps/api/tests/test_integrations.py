from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from hub.modules.integrations.router import _notion_blocks, _sync_notion_blocks


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
