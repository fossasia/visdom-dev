# Copyright 2017-present, The Visdom Authors
import uuid

from app.admin import roles
from app.models import Workspace

WORKSPACES = "/api/v1/workspaces"
KEYS = "/api/v1/keys"
RESOLVE = "/api/v1/visdom/resolve"
RESOLVE_SESSION = "/api/v1/visdom/resolve-session"


def _write_key(client, user, workspace):
    created = client.post(
        KEYS,
        json={"name": "writer", "scope": "workspace", "workspace_ids": [workspace["id"]]},
        headers=user["headers"],
    )
    assert created.status_code == 201, created.text
    return created.json()["raw_key"]


def _set(db_session, workspace, **fields):
    row = (
        db_session.query(Workspace)
        .filter(Workspace.id == uuid.UUID(workspace["id"]))
        .one()
    )
    for name, value in fields.items():
        setattr(row, name, value)
    db_session.commit()


def test_a_new_workspace_is_active(client, make_user, make_workspace, db_session):
    user = make_user()
    workspace = make_workspace(user)

    row = (
        db_session.query(Workspace)
        .filter(Workspace.id == uuid.UUID(workspace["id"]))
        .one()
    )
    assert row.is_active is True


def test_suspending_refuses_the_write_path(client, make_user, make_workspace, db_session):
    user = make_user()
    workspace = make_workspace(user)
    raw_key = _write_key(client, user, workspace)
    payload = {"workspace_slug": workspace["slug"]}

    allowed = client.post(RESOLVE, json=payload, headers={"X-API-KEY": raw_key})
    assert allowed.status_code == 200, allowed.text

    _set(db_session, workspace, is_active=False)

    refused = client.post(RESOLVE, json=payload, headers={"X-API-KEY": raw_key})
    assert refused.status_code == 403
    assert "suspended" in refused.json()["detail"].lower()


def test_suspending_refuses_the_browser_path(client, make_user, make_workspace, db_session):
    user = make_user()
    workspace = make_workspace(user)
    payload = {"workspace_slug": workspace["slug"]}

    allowed = client.post(RESOLVE_SESSION, json=payload, headers=user["headers"])
    assert allowed.status_code == 200, allowed.text

    _set(db_session, workspace, is_active=False)

    refused = client.post(RESOLVE_SESSION, json=payload, headers=user["headers"])
    assert refused.status_code == 403


def test_unsuspending_gives_the_workspace_back(client, make_user, make_workspace, db_session):
    user = make_user()
    workspace = make_workspace(user)
    payload = {"workspace_slug": workspace["slug"]}

    _set(db_session, workspace, is_active=False)
    assert client.post(RESOLVE_SESSION, json=payload, headers=user["headers"]).status_code == 403

    _set(db_session, workspace, is_active=True)
    restored = client.post(RESOLVE_SESSION, json=payload, headers=user["headers"])
    assert restored.status_code == 200
    assert restored.json()["workspace_id"] == workspace["id"]


def test_a_suspended_workspace_still_shows_in_the_listing(client, make_user, make_workspace, db_session):
    """Suspension is meant to be visible. A member who cannot get in is better
    off seeing the workspace than finding it silently gone."""
    user = make_user()
    workspace = make_workspace(user)
    _set(db_session, workspace, is_active=False)

    listed = client.get(WORKSPACES, headers=user["headers"])
    assert [ws["id"] for ws in listed.json()] == [workspace["id"]]
    assert listed.json()[0]["is_active"] is False


def test_an_unknown_role_may_change_nothing():
    assert not roles.can_change("stranger", "Workspace")
    assert roles.editable_fields("stranger", "Workspace") == set()
