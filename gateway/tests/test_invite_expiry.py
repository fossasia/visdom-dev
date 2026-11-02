# Copyright 2017-present, The Visdom Authors
"""Invites nobody answers stop holding a seat after INVITE_EXPIRY_DAYS."""
import datetime

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
