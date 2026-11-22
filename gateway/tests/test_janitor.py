# Copyright 2017-present, The Visdom Authors
import datetime
import uuid

from app.admin.janitor import (
    answered_invites,
    empty_workspaces,
    expired_links,
    findings,
    unused_keys,
)
from app.models import (
    APIKey,
    Membership,
    SharedLink,
    User,
    Workspace,
    WorkspaceInvite,
    utcnow,
)
from app.security import get_password_hash


def _user(db, email, username):
    user = User(
        id=uuid.uuid4(),
        email=email,
        username=username,
        password_hash=get_password_hash("password"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _workspace(db, slug, created_by=None):
    workspace = Workspace(
        id=uuid.uuid4(),
        name=slug,
        slug=slug,
        created_by=created_by,
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


def _key(db, owner, name, *, created_at=None, last_used_at=None, is_active=True):
    key = APIKey(
        id=uuid.uuid4(),
        user_id=owner.id,
        name=name,
        prefix=f"visdom_{name}",
        hashed_key=f"hash-{name}-{uuid.uuid4()}",
        is_active=is_active,
        created_at=created_at or utcnow(),
        last_used_at=last_used_at,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return key


def _ids(rows):
    return {row.id for row in rows}


def test_a_workspace_with_no_members_is_empty(db_session):
    owner = _user(db_session, "owner@example.com", "owner")
    empty = _workspace(db_session, "empty-ws", created_by=owner.id)

    found = empty_workspaces(db_session)

    assert _ids(found) == {empty.id}


def test_a_workspace_with_only_pending_members_is_empty(db_session):
    owner = _user(db_session, "owner@example.com", "owner")
    guest = _user(db_session, "guest@example.com", "guest")
    pending = _workspace(db_session, "pending-ws", created_by=owner.id)
    db_session.add(
        Membership(
            user_id=guest.id,
            workspace_id=pending.id,
            role="member",
            status="pending",
        )
    )
    db_session.commit()

    found = empty_workspaces(db_session)

    assert _ids(found) == {pending.id}


def test_a_workspace_with_an_active_member_is_not_empty(db_session):
    owner = _user(db_session, "owner@example.com", "owner")
    occupied = _workspace(db_session, "occupied-ws", created_by=owner.id)
    db_session.add(
        Membership(
            user_id=owner.id,
            workspace_id=occupied.id,
            role="admin",
            status="active",
        )
    )
    db_session.commit()

    assert empty_workspaces(db_session) == []


def test_a_key_created_today_is_not_flagged_when_unused(db_session):
    owner = _user(db_session, "owner@example.com", "owner")
    _key(db_session, owner, "fresh")

    assert unused_keys(db_session) == []


def test_a_key_unused_for_more_than_a_day_is_flagged(db_session):
    owner = _user(db_session, "owner@example.com", "owner")
    stale = _key(
        db_session,
        owner,
        "never-used",
        created_at=utcnow() - datetime.timedelta(days=2),
    )

    found = unused_keys(db_session)

    assert [(key.id, why) for key, why in found] == [(stale.id, "never used")]


def test_a_key_used_within_90_days_is_not_flagged(db_session):
    owner = _user(db_session, "owner@example.com", "owner")
    _key(
        db_session,
        owner,
        "recent",
        created_at=utcnow() - datetime.timedelta(days=100),
        last_used_at=utcnow() - datetime.timedelta(days=89),
    )

    assert unused_keys(db_session) == []


def test_a_key_unused_for_90_days_is_flagged(db_session):
    owner = _user(db_session, "owner@example.com", "owner")
    used = utcnow() - datetime.timedelta(days=91)
    stale = _key(
        db_session,
        owner,
        "stale",
        created_at=utcnow() - datetime.timedelta(days=100),
        last_used_at=used,
    )

    found = unused_keys(db_session)

    assert [(key.id, why) for key, why in found] == [
        (stale.id, f"last used {used.date()}")
    ]


def test_an_inactive_key_is_not_flagged(db_session):
    owner = _user(db_session, "owner@example.com", "owner")
    _key(
        db_session,
        owner,
        "revoked",
        created_at=utcnow() - datetime.timedelta(days=2),
        is_active=False,
    )

    assert unused_keys(db_session) == []


def test_an_expired_shared_link_is_flagged(db_session):
    owner = _user(db_session, "owner@example.com", "owner")
    workspace = _workspace(db_session, "shared-ws", created_by=owner.id)
    expired = SharedLink(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        role="member",
        expires_at=utcnow() - datetime.timedelta(days=1),
        invite_email="guest@example.com",
    )
    still_open = SharedLink(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        role="member",
        expires_at=utcnow() + datetime.timedelta(days=1),
    )
    forever = SharedLink(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        role="member",
        expires_at=None,
    )
    db_session.add_all([expired, still_open, forever])
    db_session.commit()

    found = expired_links(db_session)

    assert _ids(found) == {expired.id}


def test_an_invite_is_flagged_once_the_recipient_has_registered(db_session):
    owner = _user(db_session, "owner@example.com", "owner")
    _user(db_session, "guest@example.com", "guest")
    workspace = _workspace(db_session, "invite-ws", created_by=owner.id)
    answered = WorkspaceInvite(
        workspace_id=workspace.id,
        email="guest@example.com",
        role="member",
    )
    still_open = WorkspaceInvite(
        workspace_id=workspace.id,
        email="nobody@example.com",
        role="member",
    )
    db_session.add_all([answered, still_open])
    db_session.commit()

    found = answered_invites(db_session)

    assert [invite.email for invite in found] == ["guest@example.com"]


def test_findings_lists_each_cleanup_section(db_session):
    owner = _user(db_session, "owner@example.com", "owner")
    _user(db_session, "guest@example.com", "guest")
    empty = _workspace(db_session, "empty-ws", created_by=owner.id)
    _key(
        db_session,
        owner,
        "never-used",
        created_at=utcnow() - datetime.timedelta(days=2),
    )
    db_session.add(
        SharedLink(
            id=uuid.uuid4(),
            workspace_id=empty.id,
            role="member",
            expires_at=utcnow() - datetime.timedelta(hours=1),
            invite_email="guest@example.com",
        )
    )
    db_session.add(
        WorkspaceInvite(
            workspace_id=empty.id,
            email="guest@example.com",
            role="member",
        )
    )
    db_session.commit()

    sections = {section["title"]: section["rows"] for section in findings(db_session)}

    assert sections["Workspaces with no active member"] == [
        f"empty-ws (created by {owner.email})"
    ]
    assert sections["Keys nobody is using"] == [
        f"never-used ({owner.email}) - never used"
    ]
    assert any(
        row.startswith("empty-ws - guest@example.com, expired ")
        for row in sections["Shared links past their expiry"]
    )
    assert sections["Invites to people who already signed up"] == [
        "guest@example.com for empty-ws"
    ]
