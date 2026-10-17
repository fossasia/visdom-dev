
"""
Internal resolve endpoints used by the visdom server's workspace manager to map
a caller + workspace slug to a workspace id and the caller's role. Two callers:
the programmatic write path (API key) and the browser read path (session token).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import (
    enforce_api_key_workspace_scope,
    get_api_key,
    get_current_user,
    get_db,
)
from app.models import APIKey, Membership, User, Workspace

router = APIRouter(prefix="/visdom", tags=["visdom"])


class VisdomResolveRequest(BaseModel):
    workspace_slug: str


class VisdomResolveResponse(BaseModel):
    workspace_id: str
    role: str
    allowed: bool


def _lookup_workspace(db: Session, workspace_slug: str) -> Workspace:
    workspace = db.query(Workspace).filter(Workspace.slug == workspace_slug).first()
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found."
        )
    _refuse_if_suspended(workspace)
    return workspace


def _refuse_if_suspended(workspace: Workspace) -> None:
    """Stop a suspended workspace being read from or written to.

    Both paths into visdom resolve through here, so this is the one place that
    has to say no. visdom caches a resolve for its own interval, so this takes
    effect once that expires rather than at once, and a socket already open
    never resolves again.
    """
    if not workspace.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This workspace has been suspended. Contact an administrator.",
        )


def _active_membership_role(db: Session, workspace_id, user_id) -> str:
    membership = (
        db.query(Membership)
        .filter(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user_id,
            Membership.status == "active",
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not an active member of this workspace.",
        )
    return membership.role


@router.post("/resolve", response_model=VisdomResolveResponse)
def resolve_workspace(
    payload: VisdomResolveRequest,
    key_record: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Write path (python client). Resolves an API key + workspace slug to that
    workspace's id and the key owner's role, validating the key's workspace-scope
    binding and active membership. The role lets visdom map viewer to read-only.
    """
    workspace = _lookup_workspace(db, payload.workspace_slug)
    enforce_api_key_workspace_scope(db, key_record, workspace.id)
    role = _active_membership_role(db, workspace.id, key_record.user_id)
    return VisdomResolveResponse(
        workspace_id=str(workspace.id), role=role, allowed=True
    )


@router.post("/resolve-session", response_model=VisdomResolveResponse)
def resolve_session(
    payload: VisdomResolveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Browser read path. Resolves a logged-in user (from the session access token,
    which visdom forwards as a bearer token) + workspace slug to that workspace's
    id and the user's role, requiring active membership.
    """
    workspace = _lookup_workspace(db, payload.workspace_slug)
    role = _active_membership_role(db, workspace.id, current_user.id)
    return VisdomResolveResponse(
        workspace_id=str(workspace.id), role=role, allowed=True
    )
