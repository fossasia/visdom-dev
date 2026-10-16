
"""
API Key router to issue, list, and revoke programmatic authentication tokens for remote scripts.
"""

import hashlib
import secrets
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models import APIKey, Membership, User, Workspace
from app.schemas import APIKeyCreate, APIKeyCreatedResponse, APIKeyResponse
from app.usage import refuse_if_at_limit

router = APIRouter(prefix="/keys", tags=["keys"])

@router.post("", response_model=APIKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    key_in: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generates a secure API key, stores its prefix & SHA-256 hash in DB,
    and returns the raw key to the user (only displayed once).
    """
    refuse_if_at_limit(db, current_user, "api_keys")

    workspaces: List[Workspace] = []
    if key_in.scope == "workspace":
        unique_ws_ids = list(dict.fromkeys(key_in.workspace_ids))
        memberships = (
            db.query(Membership)
            .options(joinedload(Membership.workspace))
            .filter(
                Membership.user_id == current_user.id,
                Membership.workspace_id.in_(unique_ws_ids),
                Membership.status == "active",
            )
            .all()
        )
        if len(memberships) != len(unique_ws_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have active access to one or more of the specified workspaces.",
            )
        workspaces = [m.workspace for m in memberships]

    # Generate key: prefix + 32 random characters
    raw_secret = secrets.token_hex(16)
    prefix = settings.API_KEY_PREFIX
    raw_key = f"{prefix}_{raw_secret}"

    # Hash the key using SHA-256
    hashed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    # Save to database
    db_key = APIKey(
        name=key_in.name,
        prefix=f"{prefix}_{raw_secret[:6]}...",  # Displayable mask
        hashed_key=hashed_key,
        user_id=current_user.id,
        scope=key_in.scope,
        workspaces=workspaces,
        expires_at=key_in.expires_at,
    )

    db.add(db_key)
    db.commit()
    db.refresh(db_key)

    base = APIKeyResponse.model_validate(db_key, from_attributes=True)
    return APIKeyCreatedResponse(**base.model_dump(), raw_key=raw_key)


@router.get("", response_model=List[APIKeyResponse])
def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists all active API keys associated with the authenticated user."""
    return (
        db.query(APIKey)
        .options(joinedload(APIKey.workspaces))
        .filter(APIKey.user_id == current_user.id)
        .all()
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Revokes (deletes) a specific API key belonging to the user."""
    key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API Key not found or does not belong to you."
        )

    db.delete(key)
    db.commit()
