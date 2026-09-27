from typing import Annotated

from fastapi import APIRouter, Depends

from apps.api import dependencies as deps
from apps.api.usecases import auth as auth_usecase
from packages.clients.repositories.user_repository import UserRepository
from packages.config.settings import Settings
from packages.core.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    user_repository: Annotated[UserRepository, Depends(deps.get_user_repository)],
    settings: Annotated[Settings, Depends(deps.get_settings_dep)],
) -> TokenResponse:
    return await auth_usecase.register(payload, user_repository=user_repository, settings=settings)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    user_repository: Annotated[UserRepository, Depends(deps.get_user_repository)],
    settings: Annotated[Settings, Depends(deps.get_settings_dep)],
) -> TokenResponse:
    return await auth_usecase.login(payload, user_repository=user_repository, settings=settings)
