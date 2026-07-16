from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User


class AsyncJob(SQLModel, table=True):
    # Celery task id is used directly as the primary key - no need for a second id
    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    task_type: str
    status: str = Field(default="pending")  # pending | processing | done | failed
    result: Optional[str] = None  # JSON-serialized result, set once done
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    user: Optional["User"] = Relationship(back_populates="async_jobs")
