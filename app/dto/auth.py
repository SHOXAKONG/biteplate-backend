from pydantic import BaseModel, Field


class CurrentUserDTO(BaseModel):
    sub: str
    username: str
    email: str | None = None
    roles: list[str]


class LoginDTO(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshDTO(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutDTO(BaseModel):
    refresh_token: str = Field(min_length=10)


class TokenDTO(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int
    token_type: str
    scope: str | None = None
