import respx
from httpx import Response

from services.ingestion.loaders.notion_loader import NotionLoader
from services.mcp_servers.notion.client import NotionClient


@respx.mock
async def test_load_all_yields_a_raw_document_per_page() -> None:
    respx.post("https://api.notion.com/v1/search").mock(
        return_value=Response(
            200,
            json={
                "has_more": False,
                "results": [
                    {
                        "id": "page-1",
                        "url": "https://notion.so/page-1",
                        "properties": {
                            "title": {"type": "title", "title": [{"plain_text": "HR Policy"}]}
                        },
                    }
                ],
            },
        )
    )
    respx.get("https://api.notion.com/v1/blocks/page-1/children").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"plain_text": "Employees get 20 PTO days."}]},
                    }
                ]
            },
        )
    )

    client = NotionClient(access_token="fake", allowed_hosts=["api.notion.com"])
    loader = NotionLoader(client)

    documents = [doc async for doc in loader.load_all()]

    assert len(documents) == 1
    doc = documents[0]
    assert doc.document_id == "page-1"
    assert doc.title == "HR Policy"
    assert doc.source == "notion"
    assert doc.filename == "HR Policy.txt"
    assert doc.raw_bytes == b"Employees get 20 PTO days."


@respx.mock
async def test_load_all_skips_pages_with_no_content() -> None:
    respx.post("https://api.notion.com/v1/search").mock(
        return_value=Response(
            200,
            json={
                "has_more": False,
                "results": [
                    {
                        "id": "page-empty",
                        "url": "https://notion.so/page-empty",
                        "properties": {
                            "title": {"type": "title", "title": [{"plain_text": "Empty"}]}
                        },
                    }
                ],
            },
        )
    )
    respx.get("https://api.notion.com/v1/blocks/page-empty/children").mock(
        return_value=Response(200, json={"results": []})
    )

    client = NotionClient(access_token="fake", allowed_hosts=["api.notion.com"])
    loader = NotionLoader(client)

    documents = [doc async for doc in loader.load_all()]
    assert documents == []
