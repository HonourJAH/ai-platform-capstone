import hashlib
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.models import APIKey, User

KEY_PREFIX_LENGTH = 12


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    raw_key = f"sk_live_{secrets.token_urlsafe(32)}"
    hashed_key = _hash_key(raw_key)
    prefix = raw_key[:KEY_PREFIX_LENGTH]
    return raw_key, hashed_key, prefix


def verify_admin(x_admin_key: str = Header(...)) -> None:
    if not secrets.compare_digest(x_admin_key, settings.admin_bootstrap_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key"
        )


def get_api_key_user(
    x_api_key: str = Header(...),
    session: Session = Depends(get_session),
) -> User:
    hashed = _hash_key(x_api_key)
    key_row: Optional[APIKey] = session.exec(
        select(APIKey).where(APIKey.hashed_key == hashed)
    ).first()

    if key_row is None or key_row.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    user = session.get(User, key_row.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )

    return user
