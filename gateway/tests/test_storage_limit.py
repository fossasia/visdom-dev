# Copyright 2017-present, The Visdom Authors
"""New plots are refused once a workspace owner's plan is out of storage.

The gateway answers every sign-in as before and says the workspace is full;
visdom then refuses only the requests that add data. Reading and deleting keep
working, which is how an account gets back under the limit. The limit is the
owner's, since the owner's plan is the one paying.
"""
import datetime
import uuid

from app.models import User, WorkspaceUsageHour
from app.usage import MEGABYTE

RESOLVE = "/api/v1/visdom/resolve"
RESOLVE_SESSION = "/api/v1/visdom/resolve-session"
KEYS = "/api/v1/keys"
FREE_LIMIT = 1024 * MEGABYTE


def _on_plan(db, user, tier):
    record = db.query(User).filter(User.email == user["email"]).first()
    record.tier = tier
    db.commit()


def _stored(db, workspace, size):
    db.add(
        WorkspaceUsageHour(
            workspace_id=uuid.UUID(workspace["id"]),
            hour_start=datetime.datetime.now(datetime.timezone.utc).replace(
                minute=0, second=0, microsecond=0
            ),
            active_minutes=0,
            writes=0,
            broadcasts=0,
            broadcast_bytes=0,
            peak_bytes=size,
            current_bytes=size,
        )
    )
    db.commit()


def _write_key(client, user, workspace):
    created = client.post(
        KEYS,
        json={"name": "writer", "scope": "workspace", "workspace_ids": [workspace["id"]]},
        headers=user["headers"],
    )
    assert created.status_code == 201, created.text
    return created.json()["raw_key"]


def _write(client, key, workspace):
    return client.post(
        RESOLVE, json={"workspace_slug": workspace["slug"]}, headers={"X-API-KEY": key}
    )


def _full(client, key, workspace):
    answer = _write(client, key, workspace)
    assert answer.status_code == 200, answer.text
    return answer.json()["storage_full"]


def test_writes_go_through_under_the_limit(client, make_user, make_workspace, db_session):
    owner = make_user()
    ws = make_workspace(owner)
    key = _write_key(client, owner, ws)
    _on_plan(db_session, owner, "free")
    _stored(db_session, ws, FREE_LIMIT - 1)

    assert _full(client, key, ws) is None


def test_writes_are_refused_at_the_limit_and_say_why(client, make_user, make_workspace, db_session):
    owner = make_user()
    ws = make_workspace(owner)
    key = _write_key(client, owner, ws)
    _on_plan(db_session, owner, "free")
    _stored(db_session, ws, FREE_LIMIT)

    refused = _full(client, key, ws)
    assert "storage" in refused
    assert "deleting old environments" in refused


def test_space_freed_within_the_hour_lets_writes_through(
    client, make_user, make_workspace, db_session
):
    owner = make_user()
    ws = make_workspace(owner)
    key = _write_key(client, owner, ws)
    _on_plan(db_session, owner, "free")
    _stored(db_session, ws, FREE_LIMIT)
    assert _full(client, key, ws)

    row = db_session.query(WorkspaceUsageHour).one()
    row.current_bytes = FREE_LIMIT // 2
    db_session.commit()

    assert _full(client, key, ws) is None


def test_viewing_still_works_over_the_limit(client, make_user, make_workspace, db_session):
    """Otherwise there would be no way to see what to delete."""
    owner = make_user()
    ws = make_workspace(owner)
    _on_plan(db_session, owner, "free")
    _stored(db_session, ws, FREE_LIMIT * 2)

    viewed = client.post(
        RESOLVE_SESSION, json={"workspace_slug": ws["slug"]}, headers=owner["headers"]
    )
    assert viewed.status_code == 200
    assert "storage" in viewed.json()["storage_full"]


def test_an_unlimited_plan_is_never_refused(client, make_user, make_workspace, db_session):
    owner = make_user()
    ws = make_workspace(owner)
    key = _write_key(client, owner, ws)
    _on_plan(db_session, owner, "enterprise")
    _stored(db_session, ws, FREE_LIMIT * 50)

    assert _full(client, key, ws) is None


def test_storage_adds_up_across_the_owners_workspaces(client, make_user, make_workspace, db_session):
    """Each under the limit, together over it."""
    owner = make_user()
    first = make_workspace(owner)
    second = make_workspace(owner)
    key = _write_key(client, owner, first)
    _on_plan(db_session, owner, "free")
    _stored(db_session, first, FREE_LIMIT // 2 + 1)
    _stored(db_session, second, FREE_LIMIT // 2)

    assert _full(client, key, first)


def test_a_member_is_held_to_the_owners_plan_not_their_own(
    client, make_user, make_workspace, add_member, db_session
):
    """The owner's plan pays for the workspace, whoever is writing into it."""
    owner = make_user()
    member = make_user()
    ws = make_workspace(owner)
    add_member(owner, ws, member)
    key = _write_key(client, member, ws)
    _on_plan(db_session, owner, "free")
    _on_plan(db_session, member, "enterprise")
    _stored(db_session, ws, FREE_LIMIT)

    assert _full(client, key, ws)


PRO_WORKSPACE_LIMIT = 5120 * MEGABYTE


def test_one_workspace_cannot_take_the_whole_allowance(client, make_user, make_workspace, db_session):
    """Pro allows 10 GB in all but 5 GB in any one workspace."""
    owner = make_user()
    full = make_workspace(owner)
    other = make_workspace(owner)
    full_key = _write_key(client, owner, full)
    other_key = _write_key(client, owner, other)
    _on_plan(db_session, owner, "pro")
    _stored(db_session, full, PRO_WORKSPACE_LIMIT)

    refused = _full(client, full_key, full)
    assert "one workspace" in refused
    assert _full(client, other_key, other) is None


def test_a_plan_without_a_workspace_cap_falls_back_to_the_total(client, make_user, make_workspace, db_session):
    from app.models import Plan

    owner = make_user()
    ws = make_workspace(owner)
    key = _write_key(client, owner, ws)
    _on_plan(db_session, owner, "pro")
    plan = db_session.query(Plan).filter(Plan.id == "pro").one()
    plan.limits = {**plan.limits, "workspace_storage_mb": None}
    db_session.commit()
    _stored(db_session, ws, PRO_WORKSPACE_LIMIT * 3 // 2)

    assert _full(client, key, ws) is None


def test_a_trashed_workspace_still_counts_until_it_is_purged(client, make_user, make_workspace, db_session):
    """Its files are still on disk, so trashing one must not free room for another."""
    from app.models import Workspace

    owner = make_user()
    trashed = make_workspace(owner)
    live = make_workspace(owner)
    key = _write_key(client, owner, live)
    _on_plan(db_session, owner, "free")
    _stored(db_session, trashed, FREE_LIMIT)
    row = db_session.query(Workspace).filter(Workspace.id == uuid.UUID(trashed["id"])).one()
    row.trashed_at = datetime.datetime.now(datetime.timezone.utc)
    db_session.commit()

    assert _full(client, key, live)


def test_the_usage_page_shows_the_workspace_cap(client, make_user, make_workspace, db_session):
    owner = make_user()
    make_workspace(owner)
    _on_plan(db_session, owner, "pro")

    shown = client.get("/api/v1/usage", headers=owner["headers"]).json()
    assert shown["workspace_storage_limit"] == PRO_WORKSPACE_LIMIT
