# Copyright 2017-present, The Visdom Authors
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.models import User
from app.routers import workspaces as workspaces_router

WORKSPACES = "/api/v1/workspaces"


def test_create_workspace(client, make_user):
    user = make_user()
    response = client.post(
        WORKSPACES, json={"name": "NLP Labs", "slug": "nlp-labs"}, headers=user["headers"]
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "NLP Labs"
    assert data["slug"] == "nlp-labs"
    assert data["created_by"] == user["id"]
    assert data["role"] == "admin"
    assert data["starred"] is False

    members = client.get(f"{WORKSPACES}/{data['id']}/members", headers=user["headers"])
    assert members.status_code == 200
    assert members.json() == [
        {
            "user_id": user["id"],
            "invite_id": None,
            "email": user["email"],
            "role": "admin",
            "status": "active",
        }
    ]


def test_create_workspace_rejects_when_plan_limit_reached(client, make_user, make_workspace):
    user = make_user()
    existing_workspace = make_workspace(user)

    response = client.post(
        WORKSPACES,
        json={"name": "Second workspace", "slug": "second-workspace"},
        headers=user["headers"],
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Workspace limit reached for the Free plan (1 maximum)."
    workspaces = client.get(WORKSPACES, headers=user["headers"]).json()
    assert [workspace["id"] for workspace in workspaces] == [existing_workspace["id"]]


def test_concurrent_workspace_creations_cannot_exceed_plan_limit(
    file_database_client, monkeypatch
):
    client, file_sessions = file_database_client
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "quota-race@example.com", "password": "securepassword"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "quota-race@example.com", "password": "securepassword"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    db = file_sessions()
    account = db.query(User).filter(User.email == "quota-race@example.com").one()
    account.tier = "pro"
    db.commit()
    db.close()

    for number in range(9):
        created = client.post(
            WORKSPACES,
            json={"name": f"Existing {number}", "slug": f"existing-{number}"},
            headers=headers,
        )
        assert created.status_code == 201

    request_barrier = Barrier(2)
    original_lock = workspaces_router.lock_user_for_workspace_quota

    def synchronize_requests(db, user_id):
        request_barrier.wait(timeout=10)
        return original_lock(db, user_id)

    monkeypatch.setattr(workspaces_router, "lock_user_for_workspace_quota", synchronize_requests)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = [
            executor.submit(
                client.post,
                WORKSPACES,
                json={"name": f"Concurrent {number}", "slug": f"concurrent-{number}"},
                headers=headers,
            )
            for number in range(2)
        ]
        results = [response.result(timeout=15) for response in responses]

    assert sorted(result.status_code for result in results) == [201, 403]
    workspaces = client.get(WORKSPACES, headers=headers).json()
    assert len(workspaces) == 10


def test_create_workspace_duplicate_slug(client, make_user):
    first_owner = make_user()
    second_owner = make_user()
    first = client.post(
        WORKSPACES, json={"name": "First", "slug": "shared-slug"}, headers=first_owner["headers"]
    )
    assert first.status_code == 201

    duplicate = client.post(
        WORKSPACES, json={"name": "Second", "slug": "shared-slug"}, headers=second_owner["headers"]
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"] == "A workspace with this slug already exists."


def test_create_workspace_invalid_slug(client, make_user):
    user = make_user()
    response = client.post(
        WORKSPACES, json={"name": "Bad", "slug": "Not A Slug!"}, headers=user["headers"]
    )
    assert response.status_code == 422


def test_workspaces_require_authentication(client):
    assert client.get(WORKSPACES).status_code == 401
    assert client.post(WORKSPACES, json={"name": "X", "slug": "x-ws"}).status_code == 401
    assert client.delete(f"{WORKSPACES}/{uuid.uuid4()}").status_code == 401


def test_list_workspaces_scoped_to_member(client, make_user, make_workspace):
    alice = make_user()
    bob = make_user()
    alice_ws = make_workspace(alice)
    bob_ws = make_workspace(bob)

    alice_list = client.get(WORKSPACES, headers=alice["headers"]).json()
    assert [ws["id"] for ws in alice_list] == [alice_ws["id"]]

    bob_list = client.get(WORKSPACES, headers=bob["headers"]).json()
    assert [ws["id"] for ws in bob_list] == [bob_ws["id"]]


def test_delete_workspace_permissions(client, make_user, make_workspace, add_member):
    owner = make_user()
    member = make_user()
    outsider = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)

    as_outsider = client.delete(f"{WORKSPACES}/{workspace['id']}", headers=outsider["headers"])
    assert as_outsider.status_code == 404

    as_member = client.delete(f"{WORKSPACES}/{workspace['id']}", headers=member["headers"])
    assert as_member.status_code == 403
    assert as_member.json()["detail"] == "Only workspace admins can perform this action."

    as_owner = client.delete(f"{WORKSPACES}/{workspace['id']}", headers=owner["headers"])
    assert as_owner.status_code == 204

    assert client.get(WORKSPACES, headers=owner["headers"]).json() == []
    assert client.get(WORKSPACES, headers=member["headers"]).json() == []
    followup = client.get(f"{WORKSPACES}/{workspace['id']}/members", headers=owner["headers"])
    assert followup.status_code == 404


def test_star_workspace(client, make_user, make_workspace):
    user = make_user()
    stranger = make_user()
    workspace = make_workspace(user)

    starred = client.patch(
        f"{WORKSPACES}/{workspace['id']}/star", json={"starred": True}, headers=user["headers"]
    )
    assert starred.status_code == 200
    assert starred.json()["starred"] is True
    assert client.get(WORKSPACES, headers=user["headers"]).json()[0]["starred"] is True

    unstarred = client.patch(
        f"{WORKSPACES}/{workspace['id']}/star", json={"starred": False}, headers=user["headers"]
    )
    assert unstarred.json()["starred"] is False

    as_stranger = client.patch(
        f"{WORKSPACES}/{workspace['id']}/star", json={"starred": True}, headers=stranger["headers"]
    )
    assert as_stranger.status_code == 404
