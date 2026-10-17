# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Workspace router handling workspace CRUD, team memberships/roles, and
public shared-link tokens.
"""

import datetime
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing import at_limit, limit_for ,DEFAULT_TIER, get_plan
from app.config import settings
from app.dependencies import (
    commit_or_conflict,
    get_current_user,
    get_db,
    lock_user_for_workspace_quota,
)
from app.email import build_share_link_url, send_workspace_invite_email
from app.models import Membership, SharedLink, User, Workspace, WorkspaceInvite, utcnow
from app.schemas.workspace import (
    MemberInvite,
    MemberResponse,
    MemberRoleUpdate,
    MyWorkspaceResponse,
    OwnerTransfer,
    PendingInviteResponse,
    SharedLinkCreate,
    SharedLinkJoinRequest,
    SharedLinkJoinResponse,
    SharedLinkResponse,
    StarredUpdate,
    WorkspaceCreate,
)
from app.security import get_password_hash, verify_password
from app.usage import (
    hold_account,
    invites_waiting,
    invites_waiting_in,
    members_used,
    refuse_if_at_limit,
    refuse_if_full,
    refuse_if_no_seat,
    workspaces_used,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _get_membership(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Membership | None:
    return (
        db.query(Membership)
        .filter(Membership.workspace_id == workspace_id, Membership.user_id == user_id)
        .first()
    )


def _require_member(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    """Ensures the user is an active member of the workspace, else 404."""
    membership = _get_membership(db, workspace_id, user_id)
    if not membership or membership.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    return membership


def _require_admin(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    membership = _require_member(db, workspace_id, user_id)
    if membership.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace admins can perform this action.",
        )
    return membership


def _owner_of(db: Session, workspace: Workspace) -> User | None:
    if workspace.created_by is None:
        return None
    return db.query(User).filter(User.id == workspace.created_by).first()


def _to_member_response(membership: Membership) -> MemberResponse:
    return MemberResponse(
        user_id=membership.user_id,
        email=membership.user.email,
        role=membership.role,
        status=membership.status,
    )


def _invite_to_member_response(invite: WorkspaceInvite) -> MemberResponse:
    return MemberResponse(
        invite_id=invite.id,
        email=invite.email,
        role=invite.role,
        status="pending_acceptance",
    )


def _dispatch_invite_email(to_email: str, workspace_name: str, invite_url: str) -> None:
    send_workspace_invite_email(
        to_email=to_email.strip().lower(),
        workspace_name=workspace_name,
        invite_url=invite_url
    )


def _to_my_workspace_response(workspace: Workspace, membership: Membership) -> MyWorkspaceResponse:
    return MyWorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        created_by=workspace.created_by,
        role=membership.role,
        starred=bool(membership.starred),
    )


def _to_shared_link_response(link: SharedLink) -> SharedLinkResponse:
    return SharedLinkResponse(
        id=link.id,
        workspace_id=link.workspace_id,
        role=link.role,
        expires_at=link.expires_at,
        has_password=bool(link.password_hash),
        invite_email=link.invite_email,
    )


# --- WORKSPACES ---
@router.post("", response_model=MyWorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    workspace_in: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Creates a workspace and grants the creator an admin membership."""
    owner = lock_user_for_workspace_quota(db, current_user.id)
    if owner is None:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    if not owner.is_active:
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    existing = db.query(Workspace).filter(Workspace.slug == workspace_in.slug).first()
    if existing:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A workspace with this slug already exists.",
        )

    plan = get_plan(db, owner.tier or DEFAULT_TIER)
    workspace_limit = plan["limits"]["workspaces"]
    if workspace_limit is not None:
        workspaces_used = (
            db.query(Workspace.id)
            .filter(Workspace.created_by == owner.id)
            .count()
        )
        if workspaces_used >= workspace_limit:
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Workspace limit reached for the {plan['name']} plan "
                    f"({workspace_limit} maximum)."
                ),
            )

    workspace = Workspace(name=workspace_in.name, slug=workspace_in.slug, created_by=owner.id)
    db.add(workspace)
    try:
        db.flush()  # populate workspace.id before creating the membership row
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A workspace with this slug already exists.",
        ) from None

    membership = Membership(user_id=owner.id, workspace_id=workspace.id, role="admin")
    db.add(membership)
    commit_or_conflict(db, "A workspace with this slug already exists.")
    db.refresh(workspace)
    db.refresh(membership)
    return _to_my_workspace_response(workspace, membership)


@router.get("", response_model=List[MyWorkspaceResponse])
def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all workspaces the current user is an active member of."""
    rows = (
        db.query(Workspace, Membership)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .filter(Membership.user_id == current_user.id, Membership.status == "active")
        .all()
    )
    return [_to_my_workspace_response(ws, membership) for ws, membership in rows]


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deletes a workspace and its memberships/shared links. Admins only."""
    _require_admin(db, workspace_id, current_user.id)
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    db.delete(workspace)
    db.commit()


@router.patch("/{workspace_id}/star", response_model=MyWorkspaceResponse)
def set_workspace_starred(
    workspace_id: uuid.UUID,
    payload: StarredUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stars/unstars a workspace for the current user. A personal preference, not admin-gated."""
    membership = _require_member(db, workspace_id, current_user.id)
    membership.starred = payload.starred
    db.commit()
    db.refresh(membership)

    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    return _to_my_workspace_response(workspace, membership)


# --- MEMBERSHIPS ---
@router.post("/{workspace_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def invite_member(
    workspace_id: uuid.UUID,
    invite: MemberInvite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Invites a collaborator by email, creating a pending invite. Admins only."""
    _require_admin(db, workspace_id, current_user.id)
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")

    refuse_if_no_seat(db, _owner_of(db, workspace) or current_user)

    email_lower = invite.email.strip().lower()
    invitee = db.query(User).filter(User.email == email_lower).first()

    if invitee:
        if _get_membership(db, workspace_id, invitee.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of, or already has a pending invite to, this workspace.",
            )
        membership = Membership(
            user_id=invitee.id, workspace_id=workspace_id, role=invite.role, status="pending_acceptance"
        )
        db.add(membership)
        commit_or_conflict(
            db,
            "User is already a member of, or already has a pending invite to, this workspace.",
        )
        db.refresh(membership)
        _dispatch_invite_email(
            to_email=email_lower, workspace_name=workspace.name, invite_url=settings.FRONTEND_URL
        )
        return _to_member_response(membership)

    existing_invite = (
        db.query(WorkspaceInvite)
        .filter(WorkspaceInvite.workspace_id == workspace_id, WorkspaceInvite.email == email_lower)
        .first()
    )
    if existing_invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email has already been invited to this workspace.",
        )

    ws_invite = WorkspaceInvite(
        workspace_id=workspace_id, email=email_lower, role=invite.role, invited_by=current_user.id
    )
    db.add(ws_invite)
    commit_or_conflict(db, "This email has already been invited to this workspace.")
    db.refresh(ws_invite)
    _dispatch_invite_email(
        to_email=email_lower, workspace_name=workspace.name, invite_url=settings.FRONTEND_URL
    )
    return _invite_to_member_response(ws_invite)


@router.get("/{workspace_id}/members", response_model=List[MemberResponse])
def list_members(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all members and pending invites for the workspace."""
    _require_member(db, workspace_id, current_user.id)
    memberships = db.query(Membership).filter(Membership.workspace_id == workspace_id).all()
    invites = db.query(WorkspaceInvite).filter(WorkspaceInvite.workspace_id == workspace_id).all()
    return [_to_member_response(m) for m in memberships] + [_invite_to_member_response(i) for i in invites]


@router.put("/{workspace_id}/members/{user_id}", response_model=MemberResponse)
def update_member_role(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role_update: MemberRoleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Updates a collaborator's role. Admins only, and only for other members —
    no one can change their own role, and the workspace owner's role can only
    ever be set by no one at all (it's fixed once the workspace is created).
    """
    _require_admin(db, workspace_id, current_user.id)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot change your own role.",
        )

    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    if workspace.created_by == user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The workspace owner's role cannot be changed.",
        )

    membership = _get_membership(db, workspace_id, user_id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in this workspace.")
    if membership.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approve this member's request before changing their role.",
        )

    membership.role = role_update.role
    db.commit()
    db.refresh(membership)
    return _to_member_response(membership)


@router.post("/{workspace_id}/owner", response_model=MyWorkspaceResponse)
def transfer_ownership(
    workspace_id: uuid.UUID,
    payload: OwnerTransfer,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hand the workspace to another active member. Owner only.

    The new owner becomes an admin and the workspace counts against their plan
    from then on, so the move is refused when their plan has no room for it.
    The previous owner stays on as an admin, and can leave afterwards like
    anyone else.
    """
    membership = _require_admin(db, workspace_id, current_user.id)
    workspace = (
        db.query(Workspace)
        .filter(Workspace.id == workspace_id)
        .with_for_update()
        .first()
    )
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    if workspace.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the workspace owner can hand it over.",
        )
    if payload.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already own this workspace.",
        )

    target = _get_membership(db, workspace_id, payload.user_id)
    if not target or target.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Only an active member of this workspace can become its owner.",
        )

    new_owner = target.user
    hold_account(db, new_owner)
    tier = new_owner.tier or "free"
    if at_limit(db, tier, "workspaces", workspaces_used(db, new_owner)):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{new_owner.email} has no room for another workspace on the {tier} plan.",
        )
    arriving = (
        db.query(Membership)
        .filter(
            Membership.workspace_id == workspace_id,
            Membership.status == "active",
            Membership.user_id != new_owner.id,
        )
        .count()
    )
    arriving += invites_waiting_in(db, workspace_id)
    ceiling = limit_for(db, tier, "members")
    held = members_used(db, new_owner) + invites_waiting(db, new_owner)
    if ceiling is not None and held + arriving > ceiling:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{new_owner.email} has no room for this many members on the {tier} plan.",
        )

    target.role = "admin"
    workspace.created_by = new_owner.id
    db.commit()
    db.refresh(workspace)
    db.refresh(membership)
    return _to_my_workspace_response(workspace, membership)


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Removes a member from the workspace. Admins can remove non-owner members; members may
    remove (leave) themselves. The workspace owner (its creator) can only be removed by
    themselves — no other admin can kick the owner out.
    """
    is_self_leave = current_user.id == user_id
    if is_self_leave:
        requester_membership = _get_membership(db, workspace_id, current_user.id)
        if not requester_membership:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    else:
        requester_membership = _require_member(db, workspace_id, current_user.id)
        if requester_membership.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only workspace admins can remove other members.",
            )

    workspace = (
        db.query(Workspace).filter(Workspace.id == workspace_id).with_for_update().first()
    )
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    if workspace.created_by == user_id and not is_self_leave:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the workspace owner can remove themselves from the workspace.",
        )

    membership = _get_membership(db, workspace_id, user_id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in this workspace.")

    if membership.status == "active" and membership.role == "admin":
        other_admins = (
            db.query(Membership)
            .filter(
                Membership.workspace_id == workspace_id,
                Membership.role == "admin",
                Membership.status == "active",
                Membership.user_id != user_id,
            )
            .with_for_update()
            .all()
        )
        if not other_admins:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last admin of a workspace.",
            )

    db.delete(membership)
    db.commit()


@router.delete("/{workspace_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_email_invite(
    workspace_id: uuid.UUID,
    invite_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancels a pending email invite. Admins only."""
    _require_admin(db, workspace_id, current_user.id)

    invite = (
        db.query(WorkspaceInvite)
        .filter(WorkspaceInvite.id == invite_id, WorkspaceInvite.workspace_id == workspace_id)
        .first()
    )
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found in this workspace.")

    db.delete(invite)
    db.commit()


@router.post("/{workspace_id}/members/{user_id}/approve", response_model=MemberResponse)
def approve_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approves a pending shared-link join request. Admins only."""
    _require_admin(db, workspace_id, current_user.id)

    membership = _get_membership(db, workspace_id, user_id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found in this workspace.")
    if membership.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="There's no join request awaiting approval for this member.",
        )

    owner = _owner_of(db, membership.workspace)
    if owner is not None:
        refuse_if_no_seat(db, owner)

    membership.status = "active"
    db.commit()
    db.refresh(membership)
    return _to_member_response(membership)


@router.post("/{workspace_id}/members/me/accept", response_model=MemberResponse)
def accept_invite(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Accepts a direct email invite sent to the current user."""
    membership = _get_membership(db, workspace_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No invite found for this workspace.")
    if membership.status != "pending_acceptance":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="There's no pending invite for you to accept in this workspace.",
        )

    owner = _owner_of(db, membership.workspace)
    if owner is not None and owner.id != current_user.id:
        refuse_if_full(db, owner)

    membership.status = "active"
    db.commit()
    db.refresh(membership)
    return _to_member_response(membership)


@router.get("/invites/pending", response_model=List[PendingInviteResponse])
def list_pending_invites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists the current user's pending email invites."""
    rows = (
        db.query(Workspace, Membership)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .filter(Membership.user_id == current_user.id, Membership.status == "pending_acceptance")
        .all()
    )
    return [PendingInviteResponse(workspace=ws, role=membership.role) for ws, membership in rows]


# --- SHARED LINKS ---
@router.post("/{workspace_id}/share", response_model=SharedLinkResponse, status_code=status.HTTP_201_CREATED)
def create_shared_link(
    workspace_id: uuid.UUID,
    link_in: SharedLinkCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generates a secure public share token for the workspace. Admins only."""
    _require_admin(db, workspace_id, current_user.id)
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")

    invite_email = link_in.invite_email.strip().lower() if link_in.invite_email else None

    link = SharedLink(
        workspace_id=workspace_id,
        role=link_in.role,
        expires_at=link_in.expires_at,
        password_hash=get_password_hash(link_in.password) if link_in.password else None,
        invite_email=invite_email,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    if invite_email:
        _dispatch_invite_email(
            to_email=invite_email,
            workspace_name=workspace.name,
            invite_url=build_share_link_url(link.id),
        )

    return _to_shared_link_response(link)


@router.get("/{workspace_id}/share", response_model=List[SharedLinkResponse])
def list_shared_links(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all active share links for the workspace."""
    _require_member(db, workspace_id, current_user.id)
    links = db.query(SharedLink).filter(SharedLink.workspace_id == workspace_id).all()
    return [_to_shared_link_response(link) for link in links]


@router.delete("/share/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_shared_link(
    link_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revokes a public sharing link. Admins of the owning workspace only."""
    link = db.query(SharedLink).filter(SharedLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found.")

    _require_admin(db, link.workspace_id, current_user.id)

    db.delete(link)
    db.commit()


@router.post("/share/{link_id}/join", response_model=SharedLinkJoinResponse)
def join_via_shared_link(
    link_id: uuid.UUID,
    join_in: SharedLinkJoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Requests to join the workspace behind a shared link. Admins must approve."""
    link = db.query(SharedLink).filter(SharedLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found or has been revoked.")

    if link.expires_at:
        link_expires = link.expires_at
        if link_expires.tzinfo is None:
            link_expires = link_expires.replace(tzinfo=datetime.timezone.utc)
        if link_expires < utcnow():
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This shared link has expired.")

    if link.invite_email and link.invite_email != current_user.email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invite was issued to a different email address.",
        )

    if link.password_hash:
        if not join_in.password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="This shared link requires a password."
            )
        if not verify_password(join_in.password, link.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password for this shared link."
            )

    workspace = db.query(Workspace).filter(Workspace.id == link.workspace_id).first()
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="The workspace behind this link no longer exists."
        )

    existing = _get_membership(db, workspace.id, current_user.id)
    if existing:
        return SharedLinkJoinResponse(workspace=workspace, role=existing.role, status=existing.status)

    membership = Membership(
        user_id=current_user.id, workspace_id=workspace.id, role=link.role, status="pending_approval"
    )
    db.add(membership)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _get_membership(db, workspace.id, current_user.id)
        if existing is None:
            raise
        return SharedLinkJoinResponse(
            workspace=workspace, role=existing.role, status=existing.status
        )

    return SharedLinkJoinResponse(workspace=workspace, role=membership.role, status="pending_approval")
