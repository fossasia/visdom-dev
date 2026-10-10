# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Pydantic data schemas representing the payloads for user creation, token verification,
and API key provisioning. Standardizes the fields for API validation using UUID and Email.
"""

import datetime
import uuid
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.username import USERNAME_PATTERN as _USERNAME_RE

# --- USER SCHEMAS ---
USERNAME_PATTERN = _USERNAME_RE.pattern


class UserBase(BaseModel):
    email: EmailStr = Field(..., max_length=100)


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100)
    username: Optional[str] = Field(default=None, pattern=USERNAME_PATTERN)


class UserResponse(UserBase):
    id: uuid.UUID
    username: str
    tier: str
    is_active: bool
    created_at: datetime.datetime
    last_login_at: Optional[datetime.datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UsernameUpdate(BaseModel):
    username: str = Field(..., pattern=USERNAME_PATTERN)


class UsernameAvailabilityResponse(BaseModel):
    available: bool


class GeneratedUsernameResponse(BaseModel):
    username: str


class PasswordResetRequest(BaseModel):
    email: EmailStr = Field(..., max_length=100)


class PasswordResetRequested(BaseModel):
    email_enabled: bool
    support_contact: str


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=100)
    new_password: str = Field(..., min_length=6, max_length=100)


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=6, max_length=100)


# --- TOKEN SCHEMAS ---
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"



class TokenPayload(BaseModel):
    sub: Optional[str] = None  # Typically holds the User ID (UUID string)
    type: Optional[str] = None


# --- API KEY SCHEMAS ---
class APIKeyWorkspaceSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True)


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scope: Literal["org", "workspace"] = "org"
    workspace_ids: List[uuid.UUID] = Field(default_factory=list)
    expires_at: Optional[datetime.datetime] = None

    @model_validator(mode="after")
    def _validate_scope(self):
        if self.scope == "workspace" and not self.workspace_ids:
            raise ValueError("Select at least one workspace, or choose the org-wide scope.")
        if self.scope == "org" and self.workspace_ids:
            raise ValueError("workspace_ids is only valid when scope is 'workspace'.")
        return self


class APIKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    is_active: bool
    scope: str
    workspaces: List[APIKeyWorkspaceSummary] = Field(default_factory=list)
    created_at: datetime.datetime
    last_used_at: Optional[datetime.datetime] = None
    expires_at: Optional[datetime.datetime] = None

    model_config = ConfigDict(from_attributes=True)


class APIKeyCreatedResponse(APIKeyResponse):
    raw_key: str  # Only returned once on creation


# --- BILLING SCHEMAS ---
class PlanLimits(BaseModel):
    workspaces: Optional[int] = None
    members: Optional[int] = None
    api_keys: Optional[int] = None


class PlanResponse(BaseModel):
    id: str
    name: str
    price: Optional[int] = None
    limits: PlanLimits
    retention_days: Optional[int] = None
    features: List[str]


class UsageMetric(BaseModel):
    used: int
    limit: Optional[int] = None


class SubscriptionUsage(BaseModel):
    workspaces: UsageMetric
    members: UsageMetric
    api_keys: UsageMetric


class SubscriptionResponse(BaseModel):
    tier: str
    plan: PlanResponse
    usage: SubscriptionUsage


class SubscriptionUpdate(BaseModel):
    tier: Literal["free", "pro", "enterprise"]
