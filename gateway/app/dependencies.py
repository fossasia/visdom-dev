# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
FastAPI dependency injection utilities. Provides transactions for the database
and resolves user authentication via OAuth2 JWT Token extraction using UUID lookup.
"""

import datetime
import hashlib
import uuid
from typing import Generator

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import APIKey, Membership, User, utcnow
from app.security import claims_match_user, decode_token

# OAuth2 scheme looking for JWT tokens in the Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """Provides a transactional database session and closes it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def commit_or_conflict(
    db: Session,
    detail: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> None:
    """Commits, turning a constraint violation into a clean HTTP error.

    Every check-then-write in the routers leaves a window in which a concurrent
    request can write the same row first. The database still refuses the second
    write, but without this the refusal surfaces as a raw 500 instead of the same
    4xx the pre-check would have returned.
    """
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status_code, detail=detail) from None


def user_for_access_token(db: Session, token: str | None) -> User | None:
    """
    Resolves the user an access token identifies, or None if it does not
    identify one. Rejects a missing, malformed, expired or wrong-type token, an
    unknown user, and a token from a superseded session generation — logging out
    bumps `token_version`, so tokens issued before it stop resolving.

    Shared by the header-bearer path (`get_current_user`) and the cookie path
    the nginx auth gate calls, so both honour revocation identically.
    """
    if not token:
        return None

    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return None

    if payload.get("sub") is None or payload.get("type") != "access":
        return None

    # Explicit conversion for SQLite/compatibility.
    try:
        user_id = uuid.UUID(payload["sub"])
    except (TypeError, ValueError):
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not claims_match_user(payload, user):
        return None

    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Authenticates requests using JWT Access Tokens.
    Resolves the user identity by UUID lookup.
    Raises 401 Unauthorized if invalid/expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = user_for_access_token(db, token)
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    return user


LAST_USED_THROTTLE = datetime.timedelta(seconds=60)


def _touch_last_used(db: Session, key_record: APIKey) -> None:
    """Stamps last_used_at, at most once per throttle window."""
    now = utcnow()
    previous = key_record.last_used_at
    if previous is not None:
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=datetime.timezone.utc)
        if now - previous < LAST_USED_THROTTLE:
            return

    key_record.last_used_at = now
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()


def resolve_active_api_key(db: Session, raw_key: str | None) -> APIKey | None:
    """Return the APIKey for a raw key if it exists, is active, unexpired, and its
    owner is active; otherwise None. Does not raise, so callers that only need a
    yes/no answer (e.g. the reverse-proxy auth gate) can use it directly."""
    if not raw_key:
        return None
    hashed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_record = (
        db.query(APIKey)
        .filter(APIKey.hashed_key == hashed_key, APIKey.is_active.is_(True))
        .first()
    )
    if not key_record:
        return None
    if key_record.expires_at is not None:
        expires_at = key_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
        if utcnow() > expires_at:
            return None
    if not key_record.owner or not key_record.owner.is_active:
        return None
    _touch_last_used(db, key_record)
    return key_record


def get_api_key(
    x_api_key: str = Header(None, alias="X-API-KEY"),
    db: Session = Depends(get_db),
) -> APIKey:
    """
    Authenticates a request via the X-API-KEY header. Validates that the key
    exists, is active and unexpired, and that its owner is still active.
    Raises 401 otherwise. Scope/workspace binding is enforced separately via
    enforce_api_key_workspace_scope once the target workspace is known.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="X-API-KEY header is missing."
        )
    key_record = resolve_active_api_key(db, x_api_key)
    if not key_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or inactive API key.",
        )
    return key_record


def enforce_api_key_workspace_scope(
    db: Session, key: APIKey, workspace_id: uuid.UUID
) -> None:
    """
    Ensures an API key is allowed to act on a specific workspace:
      - the key's owner must be an active member of the workspace, and
      - a workspace-scoped key must have that workspace in its bound set.
    An org-scoped key works for any workspace its owner actively belongs to.
    Raises 403 otherwise.
    """
    membership = (
        db.query(Membership)
        .filter(
            Membership.workspace_id == workspace_id,
            Membership.user_id == key.user_id,
            Membership.status == "active",
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This API key's owner is not a member of this workspace.",
        )

    if key.scope == "workspace":
        bound_ids = {ws.id for ws in key.workspaces}
        if workspace_id not in bound_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This API key is not scoped to this workspace.",
            )
