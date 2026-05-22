from fastapi import APIRouter, Depends, Query, status

from app.dependencies import require_role
from app.dto.users import (
    PasswordResetDTO,
    StaffCreateDTO,
    UserCreatedDTO,
    UserDTO,
    UserEnabledUpdateDTO,
)
from app.services.keycloak_admin import keycloak_admin

router = APIRouter()


@router.get("", response_model=list[UserDTO], dependencies=[Depends(require_role("admin"))])
async def list_users(role: str | None = Query(default=None)):
    return await keycloak_admin.list_users(role=role)


@router.post(
    "",
    response_model=UserCreatedDTO,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def create_staff(dto: StaffCreateDTO) -> UserCreatedDTO:
    result = await keycloak_admin.create_user(
        username=dto.username,
        email=dto.email,
        password=dto.password,
        first_name=dto.first_name,
        last_name=dto.last_name,
        realm_roles=[dto.role],
    )
    return UserCreatedDTO(**result)


@router.patch(
    "/{user_id}/enabled",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin"))],
)
async def set_enabled(user_id: str, dto: UserEnabledUpdateDTO):
    await keycloak_admin.set_user_enabled(user_id, dto.enabled)


@router.post(
    "/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin"))],
)
async def reset_password(user_id: str, dto: PasswordResetDTO):
    await keycloak_admin.reset_password(user_id, dto.new_password)
