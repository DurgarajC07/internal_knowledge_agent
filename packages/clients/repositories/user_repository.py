"""Tenant + user persistence for signup/login. Registration creates exactly one
tenant and its first admin user atomically — the only place a Tenant row is
created outside a migration/ops script."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.clients.db_models import TenantORM, UserORM
from packages.core.enums import Role
from packages.core.schemas.user import UserRecord


def _to_record(row: UserORM) -> UserRecord:
    return UserRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        email=row.email,
        hashed_password=row.hashed_password,
        role=Role(row.role),
    )


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> UserRecord | None:
        row = await self._session.scalar(select(UserORM).where(UserORM.email == email))
        return _to_record(row) if row else None

    async def register_tenant_with_admin(
        self, *, tenant_name: str, admin_email: str, hashed_password: str
    ) -> UserRecord:
        tenant = TenantORM(name=tenant_name)
        self._session.add(tenant)
        await self._session.flush()  # populate tenant.id

        user = UserORM(
            tenant_id=tenant.id,
            email=admin_email,
            hashed_password=hashed_password,
            role=Role.ADMIN.value,
        )
        self._session.add(user)
        await self._session.flush()
        return _to_record(user)

    async def get_by_id(self, tenant_id: UUID, user_id: UUID) -> UserRecord | None:
        row = await self._session.scalar(
            select(UserORM).where(UserORM.id == user_id, UserORM.tenant_id == tenant_id)
        )
        return _to_record(row) if row else None
