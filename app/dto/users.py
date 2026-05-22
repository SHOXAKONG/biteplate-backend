from typing import Literal

from pydantic import BaseModel, Field

StaffRole = Literal["manager", "head_chef", "waiter", "cashier"]


class CustomerRegisterDTO(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)


class StaffCreateDTO(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: StaffRole


class UserCreatedDTO(BaseModel):
    id: str
    username: str
    email: str
    roles: list[str]


class UserDTO(BaseModel):
    id: str
    username: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    enabled: bool
    roles: list[str]


class UserEnabledUpdateDTO(BaseModel):
    enabled: bool


class PasswordResetDTO(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)


class ChangePasswordDTO(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)
