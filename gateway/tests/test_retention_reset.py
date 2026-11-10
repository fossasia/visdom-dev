# Copyright 2017-present, The Visdom Authors
"""One flush hook drops retention notice on any plan, bypass or owner change."""
import datetime
import uuid

import pytest

from app import bypass
from app.models import User, Workspace, utcnow


def _owner(db_session, tier="free", **extra):
    user = User(
        id=uuid.uuid4(),
        email=f"owner-{uuid.uuid4().hex[:6]}@example.com",
        username=f"owner-{uuid.uuid4().hex[:6]}",
        password_hash="x",
        tier=tier,
        **extra,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _warned(db_session, owner, slug):
    when = utcnow() - datetime.timedelta(days=10)
    workspace = Workspace(
        id=uuid.uuid4(),
        name=slug,
        slug=slug,
        created_by=owner.id,
        retention_warned_at=when,
        retention_notice={"january": when.isoformat()},
    )
    db_session.add(workspace)
    db_session.commit()
    return workspace


def _cleared(db_session, workspace):
    db_session.refresh(workspace)
    return workspace.retention_warned_at is None and workspace.retention_notice is None


def test_a_tier_change_clears_every_workspace_the_owner_has(db_session):
    owner = _owner(db_session)
    first = _warned(db_session, owner, "tier-a")
    second = _warned(db_session, owner, "tier-b")
    bystander = _warned(db_session, _owner(db_session), "tier-c")

    owner.tier = "pro"
    db_session.commit()

    assert _cleared(db_session, first)
    assert _cleared(db_session, second)
    assert not _cleared(db_session, bystander)


def test_writing_the_same_tier_keeps_the_notice(db_session):
    owner = _owner(db_session)
    workspace = _warned(db_session, owner, "same-tier")
    db_session.refresh(owner)

    owner.tier = "free"
    db_session.commit()

    assert not _cleared(db_session, workspace)


def test_a_tier_change_that_rolls_back_keeps_the_notice(db_session):
    owner = _owner(db_session)
    workspace = _warned(db_session, owner, "rolled-back")

    savepoint = db_session.begin_nested()
    owner.tier = "pro"
    db_session.flush()
    savepoint.rollback()

    assert not _cleared(db_session, workspace)


def test_ending_an_account_bypass_clears_it_and_starting_one_does_not(db_session):
    owner = _owner(db_session)
    workspace = _warned(db_session, owner, "own-bypass")

    bypass.set_for_account(db_session, owner, True)
    assert not _cleared(db_session, workspace)

    _warned_again = utcnow()
    workspace.retention_warned_at = _warned_again
    db_session.commit()
    bypass.set_for_account(db_session, owner, False)
    assert _cleared(db_session, workspace)


def test_ending_the_bypass_for_everyone_clears_every_workspace(db_session):
    first = _warned(db_session, _owner(db_session), "all-a")
    second = _warned(db_session, _owner(db_session), "all-b")

    bypass.set_for_everyone(db_session, True, by="staff@example.com")
    assert not _cleared(db_session, first)
    bypass.set_for_everyone(db_session, False, by="staff@example.com")

    assert _cleared(db_session, first)
    assert _cleared(db_session, second)


def test_a_new_owner_clears_only_that_workspace(db_session):
    owner = _owner(db_session)
    moved = _warned(db_session, owner, "moved")
    stays = _warned(db_session, owner, "stays")

    moved.created_by = _owner(db_session).id
    db_session.commit()

    assert _cleared(db_session, moved)
    assert not _cleared(db_session, stays)


def test_a_change_after_a_commit_expired_the_owner_still_clears(db_session):
    """The old tier is not loaded after a commit; that still counts as a change."""
    owner = _owner(db_session)
    workspace = _warned(db_session, owner, "expired-owner")
    db_session.expire(owner)

    owner.tier = "pro"
    db_session.commit()

    assert _cleared(db_session, workspace)


@pytest.mark.parametrize("module", ["app.payments", "app.bypass", "app.routers.billing", "app.admin.panel"])
def test_plan_changing_modules_do_not_reach_for_retention(module):
    import importlib
    import inspect

    source = inspect.getsource(importlib.import_module(module))
    nested = [
        line
        for line in source.splitlines()
        if line[:1].isspace() and line.strip().startswith(("from app import retention", "import app.retention"))
    ]
    assert nested == []
    assert "forget_warnings" not in source
