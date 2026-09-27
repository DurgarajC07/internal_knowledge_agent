from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from apps.api import dependencies as deps
from apps.api.usecases import conversations as conversations_usecase
from packages.clients.repositories.conversation_repository import ConversationRepository
from packages.core.schemas.conversation import (
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
)
from packages.core.tenant_context import TenantContext

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    tenant_ctx: Annotated[TenantContext, Depends(deps.get_tenant_context)],
    repository: Annotated[ConversationRepository, Depends(deps.get_conversation_repository)],
) -> list[ConversationOut]:
    return await conversations_usecase.list_conversations(
        tenant_ctx=tenant_ctx, repository=repository
    )


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    payload: ConversationCreate,
    tenant_ctx: Annotated[TenantContext, Depends(deps.get_tenant_context)],
    repository: Annotated[ConversationRepository, Depends(deps.get_conversation_repository)],
) -> ConversationOut:
    return await conversations_usecase.create_conversation(
        payload, tenant_ctx=tenant_ctx, repository=repository
    )


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(deps.get_tenant_context)],
    repository: Annotated[ConversationRepository, Depends(deps.get_conversation_repository)],
) -> ConversationDetailOut:
    return await conversations_usecase.get_conversation(
        conversation_id, tenant_ctx=tenant_ctx, repository=repository
    )
