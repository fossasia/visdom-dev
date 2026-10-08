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
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    stripe_customer_id = Column(String, nullable=True)
    tier = Column(String, default="free")  # free, pro, enterprise
    is_staff = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    token_version = Column(Integer, default=0, server_default="0", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_users_username_lower", func.lower(username), unique=True),
    )

    # Relationships
    api_keys = relationship("APIKey", back_populates="owner", cascade="all, delete-orphan")
    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)  # e.g., "training-cluster"
    prefix = Column(String, nullable=False)  # e.g., "visdom_live"
    hashed_key = Column(String, unique=True, index=True, nullable=False)  # SHA-256 hash
    is_active = Column(Boolean, default=True)
    scope = Column(String, nullable=False, default="org", server_default="org")
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
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
    slug = Column(String, unique=True, nullable=False, index=True)  # e.g., 'nlp-labs'
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    # Relationships
    memberships = relationship("Membership", back_populates="workspace", cascade="all, delete-orphan")
    shared_links = relationship("SharedLink", back_populates="workspace", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), primary_key=True)
    role = Column(String, default="member")  # admin, member, viewer
    starred = Column(Boolean, default=False)
    status = Column(String, nullable=False, default="active", server_default="active")

    # Relationships
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

    # Relationships
    workspace = relationship("Workspace")


class SharedLink(Base):
    __tablename__ = "shared_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # The secret public token
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    role = Column(String, default="member")  # role granted to whoever joins via this link
    expires_at = Column(DateTime(timezone=True), nullable=True)
    password_hash = Column(String, nullable=True)  # Optional link password protection
    invite_email = Column(String, nullable=True)

    # Relationships
    workspace = relationship("Workspace", back_populates="shared_links")


class AdminUser(Base):
    """A FOSSASIA staff account for the admin panel.

    Deliberately separate from User: admin access never rides on a normal user
    session, so a compromised user account cannot reach it.
    """

    __tablename__ = "admin_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="viewer", server_default="viewer")
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
