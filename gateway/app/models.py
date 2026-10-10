# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Defines the database schema and SQLAlchemy ORM models for Users and APIKeys.
Uses UUIDs for primary keys to align with the PostgreSQL production specification.
"""

import datetime
import uuid


def utcnow() -> datetime.datetime:
    """Timezone-aware replacement for the deprecated datetime.utcnow()."""
    return datetime.datetime.now(datetime.timezone.utc)
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Plan(Base):
    """A subscription tier, edited from the admin console rather than in code.

    Limits are a JSON object rather than a column each, so adding a new marker
    to what a tier includes is a change to the data instead of a migration.
    Every known marker must be present; a null value means unlimited. A plan is
    archived rather than deleted, so accounts already on it keep what it gave
    them while nobody new can be put on it.
    """

    __tablename__ = "plans"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Integer, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_public = Column(Boolean, nullable=False, default=True, server_default="true")
    archived_at = Column(DateTime(timezone=True), nullable=True)
    limits = Column(JSON, nullable=False, default=dict)
    features = Column(JSON, nullable=False, default=list)
    retention_days = Column(Integer, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    stripe_customer_id = Column(String, nullable=True)
    tier = Column(String, ForeignKey("plans.id", name="fk_users_tier_plans"), default="free")
    is_staff = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    token_version = Column(Integer, default=0, server_default="0", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    deletion_requested_at = Column(DateTime(timezone=True), nullable=True)
    trashed_at = Column(DateTime(timezone=True), nullable=True)
    trashed_by = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_users_username_lower", func.lower(username), unique=True),
    )

    api_keys = relationship("APIKey", back_populates="owner", cascade="all, delete-orphan")
    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    prefix = Column(String, nullable=False)
    hashed_key = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    scope = Column(String, nullable=False, default="org", server_default="org")
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    owner_notified_at = Column(DateTime(timezone=True), nullable=True)
    revoke_after = Column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", back_populates="api_keys")
    workspaces = relationship("Workspace", secondary="api_key_workspaces")


class APIKeyWorkspace(Base):
    __tablename__ = "api_key_workspaces"

    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id", ondelete="CASCADE"), primary_key=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    trashed_at = Column(DateTime(timezone=True), nullable=True)

    creator = relationship("User", foreign_keys=[created_by])
    memberships = relationship("Membership", back_populates="workspace", cascade="all, delete-orphan")
    shared_links = relationship("SharedLink", back_populates="workspace", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), primary_key=True)
    role = Column(String, default="member")
    starred = Column(Boolean, default=False)
    status = Column(String, nullable=False, default="active", server_default="active")

    user = relationship("User", back_populates="memberships")
    workspace = relationship("Workspace", back_populates="memberships")


class WorkspaceInvite(Base):
    __tablename__ = "workspace_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, nullable=False, index=True)
    role = Column(String, default="member")
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("workspace_id", "email", name="uq_workspace_invites_workspace_email"),
    )

    workspace = relationship("Workspace")


class SharedLink(Base):
    __tablename__ = "shared_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    role = Column(String, default="member")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    password_hash = Column(String, nullable=True)
    invite_email = Column(String, nullable=True)

    workspace = relationship("Workspace", back_populates="shared_links")


class AdminAction(Base):
    """One change a staff account made through the admin panel.

    Kept separate from the row it describes so that suspending an account leaves
    a trail even after that account is gone. The actor's email is copied in
    rather than only referenced, for the same reason.
    """

    __tablename__ = "admin_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id = Column(String, nullable=True)
    admin_email = Column(String, nullable=True)
    action = Column(String, nullable=False)
    model = Column(String, nullable=False, index=True)
    row_id = Column(String, nullable=True, index=True)
    changes = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)


class AdminUser(Base):
    """A FOSSASIA staff account for the admin panel.

    Deliberately separate from User: admin access never rides on a normal user
    session, so a compromised user account cannot reach it.
    """

    __tablename__ = "admin_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="support", server_default="support")
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_login_at = Column(DateTime(timezone=True), nullable=True)


class StaffGrant(Base):
    """One thing a superadmin has allowed admins to do.

    Either ``role`` is set, and every staff account with that role holds the
    permission, or ``admin_user_id`` is set and one account does.
    """

    __tablename__ = "staff_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    permission = Column(String, nullable=False, index=True)
    role = Column(String, nullable=True)
    admin_user_id = Column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=True
    )
    granted_by = Column(String, nullable=True)
    granted_at = Column(DateTime(timezone=True), nullable=True)


class WorkspaceUsageHour(Base):
    """What one workspace cost in one hour.

    The instances keep their counters in memory and lose them on restart, so
    what they report is only ever "since I started". This is where that becomes
    a durable record: the gateway samples on a tick, works out what changed
    since the last sample, and adds it here.

    Counters and gauges are stored side by side but do not combine the same
    way. Writes and broadcasts accumulate, so a month is their sum. Stored bytes
    is a level rather than a total, so the hour keeps the highest reading and a
    month is the largest of those, never the sum.
    """

    __tablename__ = "workspace_usage_hours"

    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    hour_start = Column(DateTime(timezone=True), primary_key=True)
    active_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    writes = Column(BigInteger, nullable=False, default=0, server_default="0")
    broadcasts = Column(BigInteger, nullable=False, default=0, server_default="0")
    broadcast_bytes = Column(BigInteger, nullable=False, default=0, server_default="0")
    peak_bytes = Column(BigInteger, nullable=False, default=0, server_default="0")

    __table_args__ = (
        Index("ix_workspace_usage_hours_hour_start", "hour_start"),
    )


class UsageBaseline(Base):
    """The last cumulative totals one instance reported about one workspace.

    Differences have to be taken per instance, not on the fan-out's sum. Three
    instances at 100 each sum to 300; if one restarts the sum falls to 202, and
    reading that fall as a reset would bill 202 for what was really 2. Kept per
    instance, a reset is visible for exactly the instance that had it.

    Kept in the database rather than in the process so that neither a restart
    nor a different worker taking the next tick loses the baseline. Losing it
    would mean taking an instance's whole lifetime count as new.
    """

    __tablename__ = "usage_baselines"

    instance = Column(String, primary_key=True)
    workspace_id = Column(String, primary_key=True)
    writes = Column(BigInteger, nullable=False, default=0, server_default="0")
    broadcasts = Column(BigInteger, nullable=False, default=0, server_default="0")
    broadcast_bytes = Column(BigInteger, nullable=False, default=0, server_default="0")


class PasswordReset(Base):
    """A link sent to choose a new password. Only a hash of the token is kept."""

    __tablename__ = "password_resets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)


class Heartbeat(Base):
    """When a background job last finished a run.

    A job that writes nothing when there is nothing to do looks the same idle as
    it does stopped. This is the one thing it always writes, so a check can tell
    the two apart.
    """

    __tablename__ = "heartbeats"

    name = Column(String, primary_key=True)
    beat_at = Column(DateTime(timezone=True), nullable=False)
