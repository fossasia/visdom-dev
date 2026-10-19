# Copyright 2017-present, The Visdom Authors
"""Removing a workspace's plot files when its rows go for good."""
import datetime
import uuid

import pytest

from app import account_deletion
from app.admin import activity
from app.models import User, Workspace, utcnow
from app.routers import workspaces as workspace_routes


@pytest.fixture
def instances(monkeypatch):
    def _set(answers):
        addresses = list(answers)
        asked = []

        def fake(address, path, body, timeout):
            assert path == activity.DROP_PATH
            asked.append((address, body))
            return answers[address]

        monkeypatch.setattr(activity, "instance_addresses", lambda: addresses)
        monkeypatch.setattr(activity, "admin_call", fake)
        return asked
    return _set


def test_every_instance_is_asked_and_the_bytes_are_added_up(instances):
    asked = instances({
        "visdom-1:8097": {"removed": True, "bytes": 300},
        "visdom-2:8097": {"removed": False, "bytes": 0},
    })
    workspace_id = uuid.uuid4()

    result = activity.drop_workspace(workspace_id)

    assert result == {"asked": 2, "removed": True, "bytes": 300}
    assert sorted(address for address, _ in asked) == ["visdom-1:8097", "visdom-2:8097"]
    assert all(str(workspace_id).encode() in body for _, body in asked)


def test_a_size_that_is_not_a_number_counts_as_nothing(instances):
    instances({
        "visdom-1:8097": {"removed": True, "bytes": "n/a"},
        "visdom-2:8097": {"removed": True, "bytes": 200},
    })

    assert activity.drop_workspace(uuid.uuid4()) == {"asked": 2, "removed": True, "bytes": 200}


def test_one_silent_instance_stops_the_removal(instances):
    instances({"visdom-1:8097": {"removed": True, "bytes": 300}, "visdom-2:8097": None})

    with pytest.raises(activity.FilesKept) as caught:
        activity.drop_workspace(uuid.uuid4())

    assert "visdom-2:8097" in str(caught.value)


def test_with_no_instances_there_is_nothing_to_ask(monkeypatch):
    monkeypatch.setattr(activity, "instance_addresses", lambda: [])
    monkeypatch.setattr(activity, "admin_call", lambda *a: pytest.fail("nothing should be asked"))

    assert activity.drop_workspace(uuid.uuid4())["removed"] is False


def test_deleting_a_workspace_removes_its_files_first(client, make_user, make_workspace, monkeypatch):
    dropped = []
    monkeypatch.setattr(workspace_routes, "drop_workspace", lambda wid: dropped.append(wid))
    owner = make_user()
    workspace = make_workspace(owner)

    response = client.delete(f"/api/v1/workspaces/{workspace['id']}", headers=owner["headers"])

    assert response.status_code == 204, response.text
    assert dropped == [uuid.UUID(workspace["id"])]


def test_a_workspace_whose_files_cannot_be_removed_stays(
    client, make_user, make_workspace, db_session, monkeypatch
):
    def refuse(_wid):
        raise activity.FilesKept("visdom-2 did not answer")

    monkeypatch.setattr(workspace_routes, "drop_workspace", refuse)
    owner = make_user()
    workspace = make_workspace(owner)

    response = client.delete(f"/api/v1/workspaces/{workspace['id']}", headers=owner["headers"])

    assert response.status_code == 503
    db_session.expire_all()
    assert db_session.query(Workspace).filter(Workspace.id == uuid.UUID(workspace["id"])).first() is not None


def _due(client, db_session, user):
    response = client.post(
        "/api/v1/auth/me/deletion", json={"password": user["password"]}, headers=user["headers"]
    )
    assert response.status_code == 202, response.text
    record = db_session.query(User).filter(User.id == uuid.UUID(user["id"])).first()
    record.deletion_requested_at = utcnow() - datetime.timedelta(days=account_deletion.GRACE_DAYS + 1)
    db_session.commit()


def test_a_deleted_account_takes_its_workspaces_files(client, make_user, make_workspace, db_session, monkeypatch):
    dropped = []
    monkeypatch.setattr(
        account_deletion,
        "drop_workspace",
        lambda wid: dropped.append(wid) or {"removed": True, "bytes": 512},
    )
    user = make_user()
    workspace = make_workspace(user)
    _due(client, db_session, user)

    assert account_deletion.erase_due(db_session) == 1
    assert dropped == [uuid.UUID(workspace["id"])]


def test_an_account_whose_files_cannot_be_removed_waits(client, make_user, make_workspace, db_session, monkeypatch):
    def refuse(_wid):
        raise activity.FilesKept("visdom-2 did not answer")

    monkeypatch.setattr(account_deletion, "drop_workspace", refuse)
    user = make_user()
    workspace = make_workspace(user)
    _due(client, db_session, user)

    assert account_deletion.erase_due(db_session) == 0
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == uuid.UUID(user["id"])).first() is not None
    assert db_session.query(Workspace).filter(Workspace.id == uuid.UUID(workspace["id"])).first() is not None


def test_nothing_is_removed_without_the_admin_key(monkeypatch):
    monkeypatch.setattr(activity.settings, "VISDOM_INTERNAL_ADMIN_KEY", "")
    monkeypatch.setattr(activity, "instance_addresses", lambda: ["visdom-1:8097"])
    monkeypatch.setattr(
        activity.urllib.request, "urlopen", lambda *a, **k: pytest.fail("nothing should be sent")
    )

    with pytest.raises(activity.FilesKept):
        activity.drop_workspace(uuid.uuid4())
