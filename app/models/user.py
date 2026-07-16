from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.api_key import APIKey
    from app.models.request_log import RequestLog
    from app.models.async_job import AsyncJob


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    tier: str = Field(default="free")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    api_keys: List["APIKey"] = Relationship(back_populates="user")
    request_logs: List["RequestLog"] = Relationship(back_populates="user")
    async_jobs: List["AsyncJob"] = Relationship(back_populates="user")
