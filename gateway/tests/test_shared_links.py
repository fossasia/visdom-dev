# Copyright 2017-present, The Visdom Authors
import uuid

WORKSPACES = "/api/v1/workspaces"


def test_create_and_list_shared_links(client, make_user, make_workspace, add_member):
    owner = make_user()
    member = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)

    default_link = client.post(
        f"{WORKSPACES}/{workspace['id']}/share", json={}, headers=owner["headers"]
    )
    assert default_link.status_code == 201
    data = default_link.json()
    assert data["workspace_id"] == workspace["id"]
    assert data["role"] == "member"
    assert data["expires_at"] is None
    assert data["has_password"] is False
    assert data["invite_email"] is None

    viewer_link = client.post(
        f"{WORKSPACES}/{workspace['id']}/share",
        json={"role": "viewer", "password": "sekret", "invite_email": "Guest@Example.com"},
        headers=owner["headers"],
    )
    assert viewer_link.status_code == 201
    assert viewer_link.json()["role"] == "viewer"
    assert viewer_link.json()["has_password"] is True
    assert viewer_link.json()["invite_email"] == "guest@example.com"

    listed = client.get(f"{WORKSPACES}/{workspace['id']}/share", headers=member["headers"])
    assert listed.status_code == 200
    assert {link["id"] for link in listed.json()} == {data["id"], viewer_link.json()["id"]}


def test_shared_link_creation_requires_admin(client, make_user, make_workspace, add_member):
    owner = make_user()
    member = make_user()
    outsider = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)

    as_member = client.post(
        f"{WORKSPACES}/{workspace['id']}/share", json={}, headers=member["headers"]
    )
    assert as_member.status_code == 403

    as_outsider = client.post(
        f"{WORKSPACES}/{workspace['id']}/share", json={}, headers=outsider["headers"]
    )
    assert as_outsider.status_code == 404


def test_join_and_approval_flow(client, make_user, make_workspace):
    owner = make_user()
    joiner = make_user()
    workspace = make_workspace(owner)
    link = client.post(
        f"{WORKSPACES}/{workspace['id']}/share", json={"role": "viewer"}, headers=owner["headers"]
    ).json()

    joined = client.post(
        f"{WORKSPACES}/share/{link['id']}/join", json={}, headers=joiner["headers"]
    )
    assert joined.status_code == 200
    assert joined.json()["workspace"]["id"] == workspace["id"]
    assert joined.json()["role"] == "viewer"
    assert joined.json()["status"] == "pending_approval"

    assert client.get(WORKSPACES, headers=joiner["headers"]).json() == []

    rejoined = client.post(
        f"{WORKSPACES}/share/{link['id']}/join", json={}, headers=joiner["headers"]
    )
    assert rejoined.status_code == 200
    assert rejoined.json()["status"] == "pending_approval"

    members = client.get(f"{WORKSPACES}/{workspace['id']}/members", headers=owner["headers"]).json()["items"]
    joiner_row = next(m for m in members if m["user_id"] == joiner["id"])
    assert joiner_row["status"] == "pending_approval"

    approved = client.post(
        f"{WORKSPACES}/{workspace['id']}/members/{joiner['id']}/approve", headers=owner["headers"]
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "active"

    workspaces = client.get(WORKSPACES, headers=joiner["headers"]).json()
    assert [ws["id"] for ws in workspaces] == [workspace["id"]]
    assert workspaces[0]["role"] == "viewer"

    re_approved = client.post(
        f"{WORKSPACES}/{workspace['id']}/members/{joiner['id']}/approve", headers=owner["headers"]
    )
    assert re_approved.status_code == 400


def test_join_password_protection(client, make_user, make_workspace):
    owner = make_user()
    joiner = make_user()
    workspace = make_workspace(owner)
    link = client.post(
        f"{WORKSPACES}/{workspace['id']}/share",
        json={"password": "sekret"},
        headers=owner["headers"],
    ).json()

    missing = client.post(
        f"{WORKSPACES}/share/{link['id']}/join", json={}, headers=joiner["headers"]
    )
    assert missing.status_code == 401
    assert missing.json()["detail"] == "This shared link requires a password."

    wrong = client.post(
        f"{WORKSPACES}/share/{link['id']}/join",
        json={"password": "nope"},
        headers=joiner["headers"],
    )
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "Incorrect password for this shared link."

    right = client.post(
        f"{WORKSPACES}/share/{link['id']}/join",
        json={"password": "sekret"},
        headers=joiner["headers"],
    )
    assert right.status_code == 200
    assert right.json()["status"] == "pending_approval"


def test_join_expired_link(client, make_user, make_workspace):
    owner = make_user()
    joiner = make_user()
    workspace = make_workspace(owner)

    naive_expired = client.post(
        f"{WORKSPACES}/{workspace['id']}/share",
        json={"expires_at": "2020-01-01T00:00:00"},
        headers=owner["headers"],
    ).json()
    aware_expired = client.post(
        f"{WORKSPACES}/{workspace['id']}/share",
        json={"expires_at": "2020-01-01T00:00:00Z"},
        headers=owner["headers"],
    ).json()
    future = client.post(
        f"{WORKSPACES}/{workspace['id']}/share",
        json={"expires_at": "2099-01-01T00:00:00Z"},
        headers=owner["headers"],
    ).json()

    for link in (naive_expired, aware_expired):
        gone = client.post(
            f"{WORKSPACES}/share/{link['id']}/join", json={}, headers=joiner["headers"]
        )
        assert gone.status_code == 410
        assert gone.json()["detail"] == "This shared link has expired."

    ok = client.post(
        f"{WORKSPACES}/share/{future['id']}/join", json={}, headers=joiner["headers"]
    )
    assert ok.status_code == 200


def test_join_link_addressed_to_someone_else(client, make_user, make_workspace):
    owner = make_user()
    invited = make_user(email="invited@example.com")
    stranger = make_user(email="stranger@example.com")
    workspace = make_workspace(owner)

    link = client.post(
        f"{WORKSPACES}/{workspace['id']}/share",
        json={"invite_email": "Invited@Example.com"},
        headers=owner["headers"],
    ).json()

    refused = client.post(
        f"{WORKSPACES}/share/{link['id']}/join", json={}, headers=stranger["headers"]
    )
    assert refused.status_code == 403
    assert refused.json()["detail"] == "This invite was issued to a different email address."

    # The address it was issued to still gets in, matched without regard to case.
    accepted = client.post(
        f"{WORKSPACES}/share/{link['id']}/join", json={}, headers=invited["headers"]
    )
    assert accepted.status_code == 200


def test_join_unaddressed_link_is_open_to_anyone(client, make_user, make_workspace):
    owner = make_user()
    anyone = make_user()
    workspace = make_workspace(owner)

    link = client.post(
        f"{WORKSPACES}/{workspace['id']}/share", json={}, headers=owner["headers"]
    ).json()

    joined = client.post(
        f"{WORKSPACES}/share/{link['id']}/join", json={}, headers=anyone["headers"]
    )
    assert joined.status_code == 200


def test_join_unknown_link(client, make_user):
    joiner = make_user()
    response = client.post(
        f"{WORKSPACES}/share/{uuid.uuid4()}/join", json={}, headers=joiner["headers"]
    )
    assert response.status_code == 404


def test_revoke_shared_link(client, make_user, make_workspace, add_member):
    owner = make_user()
    member = make_user()
    joiner = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)
    link = client.post(
        f"{WORKSPACES}/{workspace['id']}/share", json={}, headers=owner["headers"]
    ).json()

    as_member = client.delete(f"{WORKSPACES}/share/{link['id']}", headers=member["headers"])
    assert as_member.status_code == 403

    revoked = client.delete(f"{WORKSPACES}/share/{link['id']}", headers=owner["headers"])
    assert revoked.status_code == 204
    assert client.get(f"{WORKSPACES}/{workspace['id']}/share", headers=owner["headers"]).json() == []

    joined = client.post(
        f"{WORKSPACES}/share/{link['id']}/join", json={}, headers=joiner["headers"]
    )
    assert joined.status_code == 404
