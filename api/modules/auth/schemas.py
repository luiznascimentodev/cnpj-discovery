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
