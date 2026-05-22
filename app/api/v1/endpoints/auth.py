from fastapi import APIRouter, Depends, status

from app.core.security import KeycloakUser
from app.dependencies import get_current_user
from app.dto.auth import CurrentUserDTO, LoginDTO, LogoutDTO, RefreshDTO, TokenDTO
from app.dto.users import ChangePasswordDTO, CustomerRegisterDTO, UserCreatedDTO
from app.services import auth as auth_service
from app.services.keycloak_admin import keycloak_admin

router = APIRouter()


@router.get("/me", response_model=CurrentUserDTO)
async def me(user: KeycloakUser = Depends(get_current_user)) -> CurrentUserDTO:
    return CurrentUserDTO(sub=user.sub, username=user.username, email=user.email, roles=user.roles)


@router.post("/login", response_model=TokenDTO)
async def login(dto: LoginDTO) -> TokenDTO:
    tokens = await auth_service.login(dto.username, dto.password)
    return TokenDTO(**tokens)


@router.post("/refresh", response_model=TokenDTO)
async def refresh(dto: RefreshDTO) -> TokenDTO:
    tokens = await auth_service.refresh(dto.refresh_token)
    return TokenDTO(**tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(dto: LogoutDTO) -> None:
    await auth_service.logout(dto.refresh_token)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    dto: ChangePasswordDTO,
    user: KeycloakUser = Depends(get_current_user),  # noqa: B008
) -> None:
    await auth_service.change_password(user.username, dto.current_password, dto.new_password)


@router.post(
    "/register",
    response_model=UserCreatedDTO,
    status_code=status.HTTP_201_CREATED,
)
async def register_customer(dto: CustomerRegisterDTO) -> UserCreatedDTO:
    result = await keycloak_admin.create_user(
        username=dto.username,
        email=dto.email,
        password=dto.password,
        first_name=dto.first_name,
        last_name=dto.last_name,
        realm_roles=["customer"],
    )
    return UserCreatedDTO(**result)
