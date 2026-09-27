from __future__ import annotations

from uuid import UUID

from packages.clients.repositories.conversation_repository import ConversationRepository
from packages.core.exceptions import ResourceNotFoundError
from packages.core.schemas.conversation import (
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
)
from packages.core.tenant_context import TenantContext


async def list_conversations(
    *, tenant_ctx: TenantContext, repository: ConversationRepository
) -> list[ConversationOut]:
    return await repository.list_for_user(tenant_ctx.tenant_id, tenant_ctx.user_id)


async def create_conversation(
    payload: ConversationCreate, *, tenant_ctx: TenantContext, repository: ConversationRepository
) -> ConversationOut:
    return await repository.create(tenant_ctx.tenant_id, tenant_ctx.user_id, payload.title)


async def get_conversation(
    conversation_id: UUID, *, tenant_ctx: TenantContext, repository: ConversationRepository
) -> ConversationDetailOut:
    detail = await repository.get_detail(tenant_ctx.tenant_id, tenant_ctx.user_id, conversation_id)
    if detail is None:
        raise ResourceNotFoundError(f"Conversation {conversation_id} not found")
    return detail
