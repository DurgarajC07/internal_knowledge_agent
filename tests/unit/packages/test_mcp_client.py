from uuid import uuid4

import respx
from httpx import Response

from packages.clients.mcp_client import build_mcp_client
from packages.core.enums import ConnectorProvider
from packages.core.schemas.tenant_credentials import ConnectorCredential
from packages.core.schemas.tool import ToolCallContext
from tests.conftest import build_test_settings
from tests.fakes import FakeCredentialRepository


@respx.mock
async def test_call_tool_injects_tenant_credential_not_model_supplied_id() -> None:
    tenant_id, other_tenant_id = uuid4(), uuid4()
    user_id = uuid4()
    respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=Response(200, json={"files": []})
    )

    repo = FakeCredentialRepository(
        {
            (tenant_id, ConnectorProvider.GOOGLE_DRIVE): ConnectorCredential(
                tenant_id=tenant_id,
                provider=ConnectorProvider.GOOGLE_DRIVE,
                access_token="tenant-a-token",
                scopes=["drive.readonly"],
            )
        }
    )
    client = build_mcp_client(build_test_settings(), repo)

    # The tool-call arguments carry no tenant/credential field at all — the
    # model literally cannot request another tenant's data (Rule.md SS6).
    result = await client.call_tool(
        ToolCallContext(tenant_id=tenant_id, requested_by_user_id=user_id),
        ConnectorProvider.GOOGLE_DRIVE,
        "search_files",
        {"params": {"query": "contract"}},
    )
    assert result.success is True

    # A different tenant with no stored credential gets a clean failure, never
    # a fallback to someone else's token.
    result_other = await client.call_tool(
        ToolCallContext(tenant_id=other_tenant_id, requested_by_user_id=user_id),
        ConnectorProvider.GOOGLE_DRIVE,
        "search_files",
        {"params": {"query": "contract"}},
    )
    assert result_other.success is False
    assert result_other.error_message is not None


async def test_call_tool_fails_cleanly_without_raising_when_credential_missing() -> None:
    client = build_mcp_client(build_test_settings(), FakeCredentialRepository({}))
    result = await client.call_tool(
        ToolCallContext(tenant_id=uuid4(), requested_by_user_id=uuid4()),
        ConnectorProvider.NOTION,
        "search_pages",
        {"params": {"query": "policy"}},
    )
    assert result.success is False
    assert result.error_message is not None
