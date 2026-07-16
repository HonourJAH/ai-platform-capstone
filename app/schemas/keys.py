from datetime import datetime

from pydantic import BaseModel


class CreateUserRequest(BaseModel):
    email: str
    tier: str = "free"


class CreateUserResponse(BaseModel):
    user_id: int
    email: str
    tier: str


class CreateAPIKeyResponse(BaseModel):
    raw_key: str
    prefix: str
    created_at: datetime


class APIKeyInfo(BaseModel):
    id: int
    prefix: str
    created_at: datetime
    revoked_at: datetime | None
