"""Tenant-scoped conversation/message persistence. Every method takes both
`tenant_id` and `user_id` and filters by both — a user can never load another
user's (or another tenant's) conversation by guessing an ID (Rule.md SS7)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from packages.clients.db_models import ConversationORM, MessageORM
from packages.core.enums import MessageRole
from packages.core.schemas.citation import Citation
from packages.core.schemas.conversation import ConversationDetailOut, ConversationOut, MessageOut


def _conversation_out(row: ConversationORM) -> ConversationOut:
    return ConversationOut(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message_out(row: MessageORM) -> MessageOut:
    return MessageOut(
        id=row.id,
        role=MessageRole(row.role),
        content=row.content,
        citations=[Citation.model_validate(c) for c in row.citations],
        created_at=row.created_at,
    )


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, tenant_id: UUID, user_id: UUID, title: str | None) -> ConversationOut:
        row = ConversationORM(tenant_id=tenant_id, user_id=user_id, title=title)
        self._session.add(row)
        await self._session.flush()
        return _conversation_out(row)

    async def list_for_user(self, tenant_id: UUID, user_id: UUID) -> list[ConversationOut]:
        rows = await self._session.scalars(
            select(ConversationORM)
            .where(ConversationORM.tenant_id == tenant_id, ConversationORM.user_id == user_id)
            .order_by(ConversationORM.updated_at.desc())
        )
        return [_conversation_out(row) for row in rows]

    async def get_detail(
        self, tenant_id: UUID, user_id: UUID, conversation_id: UUID
    ) -> ConversationDetailOut | None:
        row = await self._session.scalar(
            select(ConversationORM)
            .where(
                ConversationORM.id == conversation_id,
                ConversationORM.tenant_id == tenant_id,
                ConversationORM.user_id == user_id,
            )
            .options(selectinload(ConversationORM.messages))
        )
        if row is None:
            return None
        return ConversationDetailOut(
            **_conversation_out(row).model_dump(),
            messages=[_message_out(m) for m in row.messages],
        )

    async def append_message(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
        citations: list[Citation],
    ) -> MessageOut:
        row = MessageORM(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            role=role.value,
            content=content,
            citations=[c.model_dump(mode="json") for c in citations],
        )
        self._session.add(row)
        await self._session.flush()
        return _message_out(row)
