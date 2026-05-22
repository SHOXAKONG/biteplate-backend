from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import KeycloakUser, verify_token
from app.database import get_session

bearer_scheme = HTTPBearer(auto_error=True)


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for s in get_session():
        yield s


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> KeycloakUser:
    return await verify_token(credentials.credentials)


def require_role(*allowed_roles: str):
    async def checker(user: KeycloakUser = Depends(get_current_user)) -> KeycloakUser:
        if not any(role in user.roles for role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(allowed_roles)}",
            )
        return user

    return checker
