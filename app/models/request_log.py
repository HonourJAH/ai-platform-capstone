from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User


class RequestLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    task_type: str = Field(index=True)
    status_code: int
    latency_ms: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: Optional["User"] = Relationship(back_populates="request_logs")
