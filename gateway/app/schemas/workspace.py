# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Pydantic data schemas for workspaces, memberships, and shared links.
Standardizes the fields for API validation using UUID and Email.
"""

import datetime
import uuid
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

RoleLiteral = Literal["admin", "member", "viewer"]


# --- WORKSPACE SCHEMAS ---
class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    created_by: Optional[uuid.UUID] = None

    model_config = ConfigDict(from_attributes=True)


class MyWorkspaceResponse(WorkspaceResponse):
    """A workspace as seen in the current user's own workspace list — includes
    their membership-specific role and starred flag alongside the workspace."""
    role: str
    starred: bool


class StarredUpdate(BaseModel):
    starred: bool


# --- MEMBERSHIP SCHEMAS ---
class MemberInvite(BaseModel):
    email: EmailStr = Field(..., max_length=100)
    role: RoleLiteral


MembershipStatus = Literal["active", "pending_approval", "pending_acceptance"]


class MemberResponse(BaseModel):
    user_id: Optional[uuid.UUID] = None
    invite_id: Optional[uuid.UUID] = None
    email: EmailStr
    role: str
    status: MembershipStatus = "active"

    model_config = ConfigDict(from_attributes=True)


class MemberPageResponse(BaseModel):
    items: List[MemberResponse]
    total: int
    next_cursor: Optional[str] = None


class PendingInviteResponse(BaseModel):
    workspace: WorkspaceResponse
    role: str


class MemberRoleUpdate(BaseModel):
    role: RoleLiteral


# --- SHARED LINK SCHEMAS ---
class SharedLinkCreate(BaseModel):
    role: RoleLiteral = "member"
    expires_at: Optional[datetime.datetime] = None
    password: Optional[str] = Field(default=None, min_length=4, max_length=100)
    invite_email: Optional[EmailStr] = None


class SharedLinkResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    role: str
    expires_at: Optional[datetime.datetime] = None
    has_password: bool
    invite_email: Optional[EmailStr] = None

    model_config = ConfigDict(from_attributes=True)


class SharedLinkJoinRequest(BaseModel):
    password: Optional[str] = None


class SharedLinkJoinResponse(BaseModel):
    workspace: WorkspaceResponse
    role: str
    status: MembershipStatus
