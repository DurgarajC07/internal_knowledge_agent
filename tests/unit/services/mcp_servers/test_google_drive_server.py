from uuid import uuid4

import respx
from httpx import Response
from mcp.types import CallToolResult, TextContent

from packages.core.enums import ConnectorProvider
from packages.core.exceptions import SSRFBlockedError
from packages.core.schemas.tenant_credentials import ConnectorCredential
from services.mcp_servers._shared.context import current_credential
from services.mcp_servers.google_drive.client import GoogleDriveClient
from services.mcp_servers.google_drive.server import build_google_drive_server
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
            provider=ConnectorProvider.GOOGLE_DRIVE,
            access_token="fake-token",
            scopes=["drive.readonly"],
        )
    )


@respx.mock
async def test_search_files_returns_formatted_results() -> None:
    _set_credential()
    respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=Response(
            200,
            json={
                "files": [
                    {
                        "id": "file-1",
                        "name": "Client X Contract.pdf",
                        "webViewLink": "https://drive.google.com/file-1",
                    }
                ]
            },
        )
    )

    server = build_google_drive_server(build_test_settings())
    result = await server.call_tool("search_files", {"params": {"query": "Client X"}})

    text = _text(result)
    assert "Client X Contract.pdf" in text
    assert "https://drive.google.com/file-1" in text


@respx.mock
async def test_get_file_content_caps_output_at_configured_limit() -> None:
    _set_credential()
    respx.get(
        "https://www.googleapis.com/drive/v3/files/file-1", params={"fields": "name,mimeType"}
    ).mock(return_value=Response(200, json={"name": "file-1.txt", "mimeType": "text/plain"}))
    respx.get("https://www.googleapis.com/drive/v3/files/file-1", params={"alt": "media"}).mock(
        return_value=Response(200, text="x" * 100)
    )

    settings = build_test_settings()
    settings.tool_output_max_chars = 10
    server = build_google_drive_server(settings)

    result = await server.call_tool("get_file_content", {"params": {"file_id": "file-1"}})
    text = _text(result)
    assert len(text) <= 10 + len("\n...(truncated)")
    assert "truncated" in text


@respx.mock
async def test_list_all_files_follows_pagination() -> None:
    respx.get("https://www.googleapis.com/drive/v3/files", params={"pageToken": "page-2"}).mock(
        return_value=Response(
            200, json={"files": [{"id": "f2", "name": "b.txt", "webViewLink": "https://x/f2"}]}
        )
    )
    respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=Response(
            200,
            json={
                "nextPageToken": "page-2",
                "files": [{"id": "f1", "name": "a.txt", "webViewLink": "https://x/f1"}],
            },
        )
    )

    client = GoogleDriveClient(access_token="fake", allowed_hosts=["www.googleapis.com"])
    files = [f async for f in client.list_all_files()]

    assert [f.file_id for f in files] == ["f1", "f2"]


@respx.mock
async def test_download_file_names_exported_google_native_docs_as_txt() -> None:
    respx.get(
        "https://www.googleapis.com/drive/v3/files/doc-1", params={"fields": "name,mimeType"}
    ).mock(
        return_value=Response(
            200, json={"name": "Q3 Plan", "mimeType": "application/vnd.google-apps.document"}
        )
    )
    respx.get(
        "https://www.googleapis.com/drive/v3/files/doc-1/export", params={"mimeType": "text/plain"}
    ).mock(return_value=Response(200, text="the plan is..."))

    client = GoogleDriveClient(access_token="fake", allowed_hosts=["www.googleapis.com"])
    content, filename = await client.download_file("doc-1")

    assert filename == "Q3 Plan.txt"
    assert content == b"the plan is..."


@respx.mock
async def test_download_file_keeps_native_filename_for_non_google_types() -> None:
    respx.get(
        "https://www.googleapis.com/drive/v3/files/pdf-1", params={"fields": "name,mimeType"}
    ).mock(return_value=Response(200, json={"name": "contract.pdf", "mimeType": "application/pdf"}))
    respx.get("https://www.googleapis.com/drive/v3/files/pdf-1", params={"alt": "media"}).mock(
        return_value=Response(200, content=b"%PDF-1.4 fake")
    )

    client = GoogleDriveClient(access_token="fake", allowed_hosts=["www.googleapis.com"])
    content, filename = await client.download_file("pdf-1")

    assert filename == "contract.pdf"
    assert content == b"%PDF-1.4 fake"


async def test_google_drive_client_rejects_non_allowlisted_host() -> None:
    client = GoogleDriveClient(access_token="fake", allowed_hosts=["some-other-host.example.com"])
    try:
        await client.search_files("anything", 5)
    except SSRFBlockedError:
        pass
    else:
        raise AssertionError("expected SSRFBlockedError for a non-allowlisted host")
