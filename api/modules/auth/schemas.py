from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserRecord(BaseModel):
    id: UUID
    email: EmailStr
    password_hash: str
    name: str
    email_verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    email_verified_at: datetime | None = None


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class EmailRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class MessageResponse(BaseModel):
    ok: bool = True
    message: str


class CsrfResponse(BaseModel):
    csrf: str


def to_user_out(user: UserRecord) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        email_verified_at=user.email_verified_at,
    )
