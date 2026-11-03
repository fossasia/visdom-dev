# Copyright 2017-present, The Visdom Authors
"""Invites nobody answers stop holding a seat after INVITE_EXPIRY_DAYS."""
import datetime
import uuid

import pytest

from app import invites
from app.models import Membership, WorkspaceInvite, utcnow


@pytest.fixture
def expiry(monkeypatch):
    monkeypatch.setattr(invites.settings, "INVITE_EXPIRY_DAYS", 30)


def _invite(client, admin, workspace, email):
    sent = client.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": email, "role": "member"},
        headers=admin["headers"],
    )
    assert sent.status_code == 201, sent.text


def _later(days):
    return utcnow() + datetime.timedelta(days=days)


def test_an_unanswered_email_invite_expires(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, "nobody-yet@example.com")

    assert invites.expire(db_session, now=_later(29)) == 0
    assert db_session.query(WorkspaceInvite).count() == 1
    assert invites.expire(db_session, now=_later(31)) == 1
    assert db_session.query(WorkspaceInvite).count() == 0


def test_an_unanswered_member_invite_expires(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    invitee = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, invitee["email"])

    def pending():
        return db_session.query(Membership).filter(Membership.status == "pending_acceptance").count()

    assert pending() == 1
    invites.expire(db_session, now=_later(29))
    assert pending() == 1
    invites.expire(db_session, now=_later(31))
    assert pending() == 0


def test_an_accepted_invite_is_never_removed(client, db_session, make_user, make_workspace, add_member, expiry):
    owner = make_user()
    member = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)

    assert invites.expire(db_session, now=_later(365)) == 0


def test_an_invite_keeps_its_age_when_the_invitee_registers(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, "late@example.com")
    sent = db_session.query(WorkspaceInvite).one().created_at

    make_user(email="late@example.com")
    membership = db_session.query(Membership).filter(Membership.status == "pending_acceptance").one()
    assert membership.invited_at == sent


def test_zero_days_turns_expiry_off(client, db_session, make_user, make_workspace, monkeypatch):
    monkeypatch.setattr(invites.settings, "INVITE_EXPIRY_DAYS", 0)
    owner = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, "forever@example.com")

    assert invites.expire(db_session, now=_later(365)) == 0


def _age(db_session, days):
    """Backdate every invite by ``days``, as if the sweep had not run yet."""
    for invite in db_session.query(WorkspaceInvite).all():
        invite.created_at = utcnow() - datetime.timedelta(days=days)
    for membership in db_session.query(Membership).filter(Membership.status == "pending_acceptance"):
        membership.invited_at = utcnow() - datetime.timedelta(days=days)
    db_session.commit()


def test_an_expired_invite_cannot_be_accepted_before_the_sweep(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    invitee = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, invitee["email"])
    _age(db_session, 31)

    accepted = client.post(f"/api/v1/workspaces/{workspace['id']}/members/me/accept", headers=invitee["headers"])
    assert accepted.status_code == 410, accepted.text
    db_session.expire_all()
    assert db_session.query(Membership).filter(Membership.user_id == uuid.UUID(invitee["id"])).count() == 0


def test_a_fresh_invite_can_still_be_accepted(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    invitee = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, invitee["email"])
    _age(db_session, 29)

    accepted = client.post(f"/api/v1/workspaces/{workspace['id']}/members/me/accept", headers=invitee["headers"])
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "active"


def test_registering_does_not_revive_an_expired_email_invite(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, "stale@example.com")
    _age(db_session, 31)

    make_user(email="stale@example.com")
    db_session.expire_all()
    assert db_session.query(Membership).filter(Membership.status == "pending_acceptance").count() == 0
    assert db_session.query(WorkspaceInvite).count() == 0


def test_invite_cleanup_runs_with_account_deletion_off(monkeypatch):
    import asyncio

    from app import main

    started = []

    async def fake_expire(hours):
        started.append(hours)

    async def fake_delete(hours):
        raise AssertionError("account deletion should be off")

    monkeypatch.setattr(main.settings, "ACCOUNT_DELETION_HOURS", 0)
    monkeypatch.setattr(main.settings, "RETENTION_SWEEP_HOURS", 0)
    monkeypatch.setattr(main.settings, "INVITE_EXPIRY_DAYS", 30)
    monkeypatch.setattr(main, "_expire_invites_forever", fake_expire)
    monkeypatch.setattr(main, "_delete_accounts_forever", fake_delete)

    async def run():
        async with main.lifespan(main.app):
            await asyncio.sleep(0)

    asyncio.run(run())
    assert started == [main.INVITE_SWEEP_HOURS]
