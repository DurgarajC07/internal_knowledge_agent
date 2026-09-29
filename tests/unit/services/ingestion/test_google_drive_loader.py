import respx
from httpx import Response

from services.ingestion.loaders.google_drive_loader import GoogleDriveLoader
from services.mcp_servers.google_drive.client import GoogleDriveClient


@respx.mock
async def test_load_all_yields_a_raw_document_per_file() -> None:
    respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=Response(
            200,
            json={
                "files": [
                    {
                        "id": "file-1",
                        "name": "contract.txt",
                        "webViewLink": "https://drive.google.com/file-1",
                    }
                ]
            },
        )
    )
    respx.get(
        "https://www.googleapis.com/drive/v3/files/file-1", params={"fields": "name,mimeType"}
    ).mock(return_value=Response(200, json={"name": "contract.txt", "mimeType": "text/plain"}))
    respx.get("https://www.googleapis.com/drive/v3/files/file-1", params={"alt": "media"}).mock(
        return_value=Response(200, text="The retainer fee is $12,000.")
    )

    client = GoogleDriveClient(access_token="fake", allowed_hosts=["www.googleapis.com"])
    loader = GoogleDriveLoader(client)

    documents = [doc async for doc in loader.load_all()]

    assert len(documents) == 1
    doc = documents[0]
    assert doc.document_id == "file-1"
    assert doc.title == "contract.txt"
    assert doc.source == "google_drive"
    assert doc.url_or_path == "https://drive.google.com/file-1"
    assert doc.raw_bytes == b"The retainer fee is $12,000."


@respx.mock
async def test_load_all_skips_empty_files() -> None:
    respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=Response(
            200, json={"files": [{"id": "empty-1", "name": "empty.txt", "webViewLink": ""}]}
        )
    )
    respx.get(
        "https://www.googleapis.com/drive/v3/files/empty-1", params={"fields": "name,mimeType"}
    ).mock(return_value=Response(200, json={"name": "empty.txt", "mimeType": "text/plain"}))
    respx.get("https://www.googleapis.com/drive/v3/files/empty-1", params={"alt": "media"}).mock(
        return_value=Response(200, text="")
    )

    client = GoogleDriveClient(access_token="fake", allowed_hosts=["www.googleapis.com"])
    loader = GoogleDriveLoader(client)

    documents = [doc async for doc in loader.load_all()]
    assert documents == []
