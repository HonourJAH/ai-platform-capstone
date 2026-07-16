from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User


class APIKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    hashed_key: str = Field(index=True, unique=True)
    prefix: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revoked_at: Optional[datetime] = None

    user: Optional["User"] = Relationship(back_populates="api_keys")
