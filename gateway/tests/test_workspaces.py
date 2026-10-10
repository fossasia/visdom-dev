# Copyright 2017-present, The Visdom Authors
import uuid

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
    assert members.json()["items"] == [
        {
            "user_id": user["id"],
            "invite_id": None,
            "email": user["email"],
            "role": "admin",
            "status": "active",
        }
    ]


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
