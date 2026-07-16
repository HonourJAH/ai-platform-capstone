from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.models import APIKey, User
from app.schemas.keys import (
    APIKeyInfo,
    CreateAPIKeyResponse,
    CreateUserRequest,
    CreateUserResponse,
)
from app.services.auth import generate_api_key, verify_admin

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin)]
)


@router.post(
    "/users", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED
)
def create_user(payload: CreateUserRequest, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User already exists"
        )

    user = User(email=payload.email, tier=payload.tier)
    session.add(user)
    session.commit()
    session.refresh(user)
    return CreateUserResponse(user_id=user.id, email=user.email, tier=user.tier)


@router.post(
    "/users/{user_id}/keys",
    response_model=CreateAPIKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_api_key(user_id: int, session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    raw_key, hashed_key, prefix = generate_api_key()
    key_row = APIKey(user_id=user_id, hashed_key=hashed_key, prefix=prefix)
    session.add(key_row)
    session.commit()
    session.refresh(key_row)

    return CreateAPIKeyResponse(
        raw_key=raw_key, prefix=prefix, created_at=key_row.created_at
    )


@router.get("/users/{user_id}/keys", response_model=list[APIKeyInfo])
def list_api_keys(user_id: int, session: Session = Depends(get_session)):
    keys = session.exec(select(APIKey).where(APIKey.user_id == user_id)).all()
    return keys


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(key_id: int, session: Session = Depends(get_session)):
    key_row = session.get(APIKey, key_id)
    if key_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Key not found"
        )

    key_row.revoked_at = datetime.now(timezone.utc)
    session.add(key_row)
    session.commit()
