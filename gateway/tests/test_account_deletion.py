# Copyright 2017-present, The Visdom Authors
import datetime
import uuid

from app import account_deletion
from app.models import AdminAction, APIKey, Membership, User, Workspace, utcnow

AUTH = "/api/v1/auth"
WORKSPACES = "/api/v1/workspaces"


def _preview(client, user):
    response = client.get(f"{AUTH}/me/deletion", headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def _request(client, user, password=None):
    return client.post(
        f"{AUTH}/me/deletion",
        json={"password": password or user["password"]},
        headers=user["headers"],
    )


def _login(client, user):
    return client.post(f"{AUTH}/login", data={"username": user["email"], "password": user["password"]})


def _record(db_session, user):
    db_session.expire_all()
    return db_session.query(User).filter(User.id == uuid.UUID(user["id"])).first()


def _age(db_session, user, days):
    record = _record(db_session, user)
    record.deletion_requested_at = utcnow() - datetime.timedelta(days=days)
    db_session.commit()


def _make_key(client, user):
    created = client.post("/api/v1/keys", json={"name": "k"}, headers=user["headers"])
    assert created.status_code == 201, created.text
    return created.json()["raw_key"]


def test_preview_lists_what_goes_with_the_account(client, make_user, make_workspace, add_member):
    user = make_user()
    other = make_user()
    alone = make_workspace(user, name="Alone")
    theirs = make_workspace(other)
    add_member(other, theirs, user)

    preview = _preview(client, user)
    assert preview["grace_days"] == account_deletion.GRACE_DAYS
    assert preview["blockers"] == []
    assert [ws["id"] for ws in preview["leaving_with"]] == [alone["id"]]


def test_an_owner_with_a_team_must_hand_over_first(client, make_user, make_workspace, add_member):
    owner = make_user()
    member = make_user()
    workspace = make_workspace(owner, name="Team")
    add_member(owner, workspace, member)

    preview = _preview(client, owner)
    assert [ws["id"] for ws in preview["blockers"]] == [workspace["id"]]
    assert "owner" in preview["blockers"][0]["reason"]

    refused = _request(client, owner)
    assert refused.status_code == 409
    assert "Team" in refused.json()["detail"]


def test_the_only_admin_must_make_another_admin_first(client, make_user, make_workspace, add_member):
    owner = make_user()
    admin = make_user()
    member = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, admin, role="admin")
    add_member(owner, workspace, member)
    left = client.delete(f"{WORKSPACES}/{workspace['id']}/members/{owner['id']}", headers=owner["headers"])
    assert left.status_code == 204

    preview = _preview(client, admin)
    assert [ws["id"] for ws in preview["blockers"]] == [workspace["id"]]
    assert "admin" in preview["blockers"][0]["reason"]
    assert _preview(client, member)["blockers"] == []


def test_a_wrong_password_changes_nothing(client, make_user, db_session):
    user = make_user()
    refused = _request(client, user, password="not-the-password")
    assert refused.status_code == 400
    assert _record(db_session, user).deletion_requested_at is None


def test_a_request_closes_sessions_and_keys(client, make_user, db_session):
    user = make_user()
    raw_key = _make_key(client, user)

    scheduled = _request(client, user)
    assert scheduled.status_code == 202, scheduled.text
    assert scheduled.json()["delete_after"]
    assert _record(db_session, user).deletion_requested_at is not None

    assert client.get(f"{AUTH}/me", headers=user["headers"]).status_code == 401
    assert client.get(f"{AUTH}/key-check", headers={"X-API-KEY": raw_key}).status_code == 401


def test_signing_in_cancels_the_request(client, make_user, db_session):
    user = make_user()
    raw_key = _make_key(client, user)
    assert _request(client, user).status_code == 202

    signed_in = _login(client, user)
    assert signed_in.status_code == 200
    assert signed_in.json()["deletion_cancelled"] is True
    assert _record(db_session, user).deletion_requested_at is None
    assert client.get(f"{AUTH}/key-check", headers={"X-API-KEY": raw_key}).status_code == 200

    again = _login(client, user)
    assert again.json()["deletion_cancelled"] is False


def test_nothing_is_removed_before_the_deadline(client, make_user, make_workspace, db_session):
    user = make_user()
    make_workspace(user)
    assert _request(client, user).status_code == 202
    _age(db_session, user, account_deletion.GRACE_DAYS - 1)

    assert account_deletion.erase_due(db_session) == 0
    assert _record(db_session, user) is not None


def test_after_the_deadline_the_account_and_its_lone_workspaces_go(
    client, make_user, make_workspace, add_member, db_session
):
    user = make_user()
    other = make_user()
    alone = make_workspace(user)
    shared = make_workspace(other)
    add_member(other, shared, user)
    _make_key(client, user)
    assert _request(client, user).status_code == 202
    _age(db_session, user, account_deletion.GRACE_DAYS + 1)

    assert account_deletion.erase_due(db_session) == 1

    db_session.expire_all()
    assert _record(db_session, user) is None
    assert db_session.query(Workspace).filter(Workspace.id == uuid.UUID(alone["id"])).first() is None
    assert db_session.query(Workspace).filter(Workspace.id == uuid.UUID(shared["id"])).first() is not None
    assert db_session.query(APIKey).filter(APIKey.user_id == uuid.UUID(user["id"])).count() == 0

    trail = db_session.query(AdminAction).filter(AdminAction.row_id == user["id"]).one()
    assert trail.action == "delete"
    assert trail.changes["workspaces_removed"] == [alone["slug"]]

    members = client.get(f"{WORKSPACES}/{shared['id']}/members", headers=other["headers"]).json()
    assert [m["user_id"] for m in members] == [other["id"]]


def test_a_workspace_they_had_left_passes_to_an_admin(
    client, make_user, make_workspace, add_member, db_session
):
    owner = make_user()
    admin = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, admin, role="admin")
    left = client.delete(f"{WORKSPACES}/{workspace['id']}/members/{owner['id']}", headers=owner["headers"])
    assert left.status_code == 204

    assert _request(client, owner).status_code == 202
    _age(db_session, owner, account_deletion.GRACE_DAYS + 1)
    assert account_deletion.erase_due(db_session) == 1

    db_session.expire_all()
    row = db_session.query(Workspace).filter(Workspace.id == uuid.UUID(workspace["id"])).first()
    assert row.created_by == uuid.UUID(admin["id"])


def test_a_blocker_that_appears_later_stops_the_removal(client, make_user, make_workspace, db_session):
    user = make_user()
    other = make_user()
    workspace = make_workspace(user)
    assert _request(client, user).status_code == 202

    db_session.add(
        Membership(
            user_id=uuid.UUID(other["id"]),
            workspace_id=uuid.UUID(workspace["id"]),
            role="member",
        )
    )
    db_session.commit()
    _age(db_session, user, account_deletion.GRACE_DAYS + 1)

    assert account_deletion.erase_due(db_session) == 0
    assert _record(db_session, user) is not None
