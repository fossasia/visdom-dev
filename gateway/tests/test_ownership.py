# Copyright 2017-present, The Visdom Authors
import uuid

from app.models import Workspace

WORKSPACES = "/api/v1/workspaces"


def _hand_over(client, workspace, owner, to):
    return client.post(
        f"{WORKSPACES}/{workspace['id']}/owner",
        json={"user_id": to["id"]},
        headers=owner["headers"],
    )


def _set_tier(db_session, user, tier):
    from app.models import User

    record = db_session.query(User).filter(User.email == user["email"]).first()
    record.tier = tier
    db_session.commit()


def test_owner_hands_over_to_a_member(client, make_user, make_workspace, add_member, db_session):
    owner = make_user()
    member = make_user(tier="pro")
    workspace = make_workspace(owner)
    add_member(owner, workspace, member, role="viewer")

    handed = _hand_over(client, workspace, owner, member)
    assert handed.status_code == 200, handed.text
    assert handed.json()["created_by"] == member["id"]
    assert handed.json()["role"] == "admin"

    members = client.get(f"{WORKSPACES}/{workspace['id']}/members", headers=owner["headers"]).json()
    roles = {m["user_id"]: m["role"] for m in members}
    assert roles == {owner["id"]: "admin", member["id"]: "admin"}

    row = db_session.query(Workspace).filter(Workspace.id == uuid.UUID(handed.json()["id"])).first()
    db_session.refresh(row)
    assert row.created_by == uuid.UUID(member["id"])


def test_the_previous_owner_can_then_be_managed(client, make_user, make_workspace, add_member):
    owner = make_user()
    member = make_user(tier="pro")
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)
    assert _hand_over(client, workspace, owner, member).status_code == 200

    demoted = client.put(
        f"{WORKSPACES}/{workspace['id']}/members/{owner['id']}",
        json={"role": "member"},
        headers=member["headers"],
    )
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "member"


def test_only_the_owner_can_hand_over(client, make_user, make_workspace, add_member):
    owner = make_user()
    admin = make_user(tier="pro")
    member = make_user(tier="pro")
    workspace = make_workspace(owner)
    add_member(owner, workspace, admin, role="admin")
    add_member(owner, workspace, member)

    assert _hand_over(client, workspace, admin, member).status_code == 403
    assert _hand_over(client, workspace, member, admin).status_code == 403


def test_cannot_hand_over_to_yourself_or_an_outsider(client, make_user, make_workspace):
    owner = make_user()
    outsider = make_user(tier="pro")
    workspace = make_workspace(owner)

    assert _hand_over(client, workspace, owner, owner).status_code == 400
    assert _hand_over(client, workspace, owner, outsider).status_code == 404


def test_cannot_hand_over_to_a_pending_member(client, make_user, make_workspace):
    owner = make_user()
    invitee = make_user(tier="pro")
    workspace = make_workspace(owner)
    invited = client.post(
        f"{WORKSPACES}/{workspace['id']}/members",
        json={"email": invitee["email"], "role": "member"},
        headers=owner["headers"],
    )
    assert invited.status_code == 201

    assert _hand_over(client, workspace, owner, invitee).status_code == 404


def test_refused_when_the_new_owner_has_no_room(client, make_user, make_workspace, add_member, db_session):
    owner = make_user()
    member = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)

    own = client.post(WORKSPACES, json={"name": "Mine", "slug": "mine-already"}, headers=member["headers"])
    assert own.status_code == 201

    refused = _hand_over(client, workspace, owner, member)
    assert refused.status_code == 402
    assert member["email"] in refused.json()["detail"]

    _set_tier(db_session, member, "pro")
    assert _hand_over(client, workspace, owner, member).status_code == 200


def test_refused_when_the_members_would_not_fit(client, make_user, make_workspace, add_member, db_session):
    owner = make_user()
    member = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)
    for _ in range(3):
        add_member(owner, workspace, make_user())

    refused = _hand_over(client, workspace, owner, member)
    assert refused.status_code == 402
    assert "members" in refused.json()["detail"]
