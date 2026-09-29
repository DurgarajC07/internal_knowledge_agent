import json
from uuid import uuid4

import httpx
import respx
from httpx import Response
from mcp.types import CallToolResult, TextContent

from packages.core.enums import ConnectorProvider
from packages.core.exceptions import SSRFBlockedError
from packages.core.schemas.tenant_credentials import ConnectorCredential
from services.mcp_servers._shared.context import current_credential
from services.mcp_servers.notion.client import NotionClient
from services.mcp_servers.notion.server import build_notion_server
from tests.conftest import build_test_settings


def _text(result: object) -> str:
    assert isinstance(result, CallToolResult)
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


def _set_credential() -> None:
    current_credential.set(
        ConnectorCredential(
            tenant_id=uuid4(),
            provider=ConnectorProvider.NOTION,
            access_token="fake-notion-token",
            scopes=["read"],
        )
    )


@respx.mock
async def test_search_pages_returns_formatted_results() -> None:
    _set_credential()
    respx.post("https://api.notion.com/v1/search").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {
                        "id": "page-1",
                        "url": "https://notion.so/page-1",
                        "properties": {
                            "title": {"type": "title", "title": [{"plain_text": "HR Policy"}]}
                        },
                    }
                ]
            },
        )
    )

    server = build_notion_server(build_test_settings())
    result = await server.call_tool("search_pages", {"params": {"query": "HR policy"}})

    text = _text(result)
    assert "HR Policy" in text
    assert "https://notion.so/page-1" in text


@respx.mock
async def test_search_pages_returns_message_when_no_results() -> None:
    _set_credential()
    respx.post("https://api.notion.com/v1/search").mock(
        return_value=Response(200, json={"results": []})
    )

    server = build_notion_server(build_test_settings())
    result = await server.call_tool("search_pages", {"params": {"query": "nonexistent"}})

    assert _text(result) == "No matching pages found."


@respx.mock
async def test_get_page_content_concatenates_block_rich_text() -> None:
    _set_credential()
    respx.get("https://api.notion.com/v1/blocks/page-1/children").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"plain_text": "The retainer fee is $12,000."}]
                        },
                    },
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"plain_text": "Due monthly."}]},
                    },
                ]
            },
        )
    )

    server = build_notion_server(build_test_settings())
    result = await server.call_tool("get_page_content", {"params": {"page_id": "page-1"}})

    text = _text(result)
    assert "The retainer fee is $12,000." in text
    assert "Due monthly." in text


@respx.mock
async def test_list_all_pages_follows_pagination() -> None:
    def handler(request: httpx.Request) -> Response:
        body = json.loads(request.content)
        if body.get("start_cursor") == "cursor-2":
            return Response(
                200,
                json={
                    "has_more": False,
                    "results": [
                        {
                            "id": "page-2",
                            "url": "https://notion.so/page-2",
                            "properties": {
                                "title": {"type": "title", "title": [{"plain_text": "Page Two"}]}
                            },
                        }
                    ],
                },
            )
        return Response(
            200,
            json={
                "has_more": True,
                "next_cursor": "cursor-2",
                "results": [
                    {
                        "id": "page-1",
                        "url": "https://notion.so/page-1",
                        "properties": {
                            "title": {"type": "title", "title": [{"plain_text": "Page One"}]}
                        },
                    }
                ],
            },
        )

    respx.post("https://api.notion.com/v1/search").mock(side_effect=handler)

    client = NotionClient(access_token="fake", allowed_hosts=["api.notion.com"])
    pages = [p async for p in client.list_all_pages()]

    assert [p.page_id for p in pages] == ["page-1", "page-2"]


async def test_notion_client_rejects_non_allowlisted_host() -> None:
    client = NotionClient(access_token="fake", allowed_hosts=["some-other-host.example.com"])
    try:
        await client.search_pages("anything", 5)
    except SSRFBlockedError:
        pass
    else:
        raise AssertionError("expected SSRFBlockedError for a non-allowlisted host")
