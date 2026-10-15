# Copyright 2017-present, The Visdom Authors
"""Changing and removing memberships from the console.

The rules here matter more than the plumbing. A console that could leave a
workspace with nobody able to administer it would be a way around the product's
own rules rather than a way to administer them.
"""
import asyncio
import uuid

import pytest
from starlette.exceptions import HTTPException

from app.admin import roles
from app.admin.panel import MembershipAdmin
from app.models import Membership, User, Workspace


class FakeRequest:
    def __init__(self, role):
        self.session = {"admin_role": role}


@pytest.fixture
def workspace_with_members(db_session, monkeypatch):
    """An owner who is admin, a second admin, and an ordinary member."""
    from sqlalchemy.orm import sessionmaker

    from app.admin import panel

    bind = db_session.get_bind()
    monkeypatch.setattr(panel, "SessionLocal", sessionmaker(bind=bind))

    owner = User(
        id=uuid.uuid4(), email="owner@example.com", username="owner", password_hash="x"
    )
    second = User(
        id=uuid.uuid4(), email="second@example.com", username="second", password_hash="x"
    )
    plain = User(
        id=uuid.uuid4(), email="plain@example.com", username="plain", password_hash="x"
    )
    workspace = Workspace(
        id=uuid.uuid4(), name="Shared", slug="shared", created_by=owner.id
    )
    rows = {
        "owner": Membership(
            user_id=owner.id, workspace_id=workspace.id, role="admin", status="active"
        ),
        "second": Membership(
            user_id=second.id, workspace_id=workspace.id, role="admin", status="active"
        ),
        "plain": Membership(
            user_id=plain.id, workspace_id=workspace.id, role="member", status="active"
        ),
    }
    db_session.add_all([owner, second, plain, workspace, *rows.values()])
    db_session.commit()
    return {"workspace": workspace, **rows}


def change_role(membership, new_role, role=roles.SUPERADMIN):
    asyncio.run(
        MembershipAdmin().on_model_change(
            {"role": new_role}, membership, False, FakeRequest(role)
        )
    )


def remove(membership, role=roles.SUPERADMIN):
    asyncio.run(MembershipAdmin().on_model_delete(membership, FakeRequest(role)))


def may_edit(role, membership):
    return asyncio.run(MembershipAdmin().check_can_edit(FakeRequest(role), membership))


def may_remove(role, membership):
    return asyncio.run(MembershipAdmin().check_can_delete(FakeRequest(role), membership))


def test_an_ordinary_member_can_be_removed(workspace_with_members):
    remove(workspace_with_members["plain"])


def test_an_admin_can_be_removed_while_another_remains(workspace_with_members):
    remove(workspace_with_members["second"])


def test_the_last_admin_cannot_be_removed(db_session, workspace_with_members):
    """The same rule the API applies when a member removes another."""
    db_session.delete(workspace_with_members["second"])
    db_session.commit()

    with pytest.raises(HTTPException) as refused:
        remove(workspace_with_members["owner"])

    assert "last admin" in refused.value.detail


def test_the_last_admin_cannot_be_demoted_either(db_session, workspace_with_members):
    """Demoting the last admin leaves the workspace in the same state as
    removing them, so it has to be refused for the same reason."""
    db_session.delete(workspace_with_members["owner"])
    db_session.commit()

    with pytest.raises(HTTPException) as refused:
        change_role(workspace_with_members["second"], "member")

    assert "last admin" in refused.value.detail


def test_the_owner_is_always_an_admin(workspace_with_members):
    """The API refuses this too, and it is the rule that guarantees every
    workspace has an admin at all."""
    with pytest.raises(HTTPException) as refused:
        change_role(workspace_with_members["owner"], "member")

    assert "owner" in refused.value.detail


def test_promoting_someone_is_never_refused(workspace_with_members):
    change_role(workspace_with_members["plain"], "admin")


def test_support_cannot_remove_a_membership(workspace_with_members):
    plain = workspace_with_members["plain"]

    assert not may_remove(roles.SUPPORT, plain)
    assert may_remove(roles.SUPERADMIN, plain)


def test_support_may_still_change_a_role(workspace_with_members):
    plain = workspace_with_members["plain"]

    assert may_edit(roles.SUPPORT, plain)
    change_role(plain, "viewer", role=roles.SUPPORT)


def test_an_admin_can_do_both(workspace_with_members):
    plain = workspace_with_members["plain"]

    assert may_edit(roles.ADMIN, plain)
    assert may_remove(roles.ADMIN, plain)


def test_an_unknown_role_can_do_neither(workspace_with_members):
    plain = workspace_with_members["plain"]

    assert not may_edit("stranger", plain)
    assert not may_remove("stranger", plain)
