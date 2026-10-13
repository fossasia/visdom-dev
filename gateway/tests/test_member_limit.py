# Copyright 2017-present, The Visdom Authors
"""The team member limit, and the ways round it that used to work.

The limit was checked only when an invite was sent and counted only the people
who had already accepted. So an owner under the limit could send any number of
invites and keep everyone who accepted, and a join through a shared link was
never checked at all. An invite now holds a seat from the moment it is sent.
"""
import uuid

from app.models import Membership, User

WORKSPACES = "/api/v1/workspaces"
FREE_SEATS = 3


def _workspace(client, owner, slug=None):
    slug = slug or f"lab-{uuid.uuid4().hex[:8]}"
    made = client.post(WORKSPACES, json={"name": "Lab", "slug": slug}, headers=owner["headers"])
    assert made.status_code == 201, made.text
    return made.json()


def _invite(client, admin, workspace, email, role="member"):
    return client.post(
        f"{WORKSPACES}/{workspace['id']}/members",
        json={"email": email, "role": role},
        headers=admin["headers"],
    )


def _accept(client, user, workspace):
    return client.post(f"{WORKSPACES}/{workspace['id']}/members/me/accept", headers=user["headers"])


def _on_plan(db_session, user, tier):
    record = db_session.query(User).filter(User.email == user["email"]).first()
    record.tier = tier
    db_session.commit()


def test_a_full_team_refuses_another_invite(client, make_user):
    owner = make_user()
    workspace = _workspace(client, owner)
    for _ in range(FREE_SEATS):
        member = make_user()
        assert _invite(client, owner, workspace, member["email"]).status_code == 201
        assert _accept(client, member, workspace).status_code == 200

    refused = _invite(client, owner, workspace, make_user()["email"])
    assert refused.status_code == 402
    assert "3 team members" in refused.json()["detail"]


def test_invites_still_waiting_hold_their_seats(client, make_user):
    owner = make_user()
    workspace = _workspace(client, owner)
    assert _invite(client, owner, workspace, make_user()["email"]).status_code == 201
    assert _invite(client, owner, workspace, make_user()["email"]).status_code == 201
    assert _invite(client, owner, workspace, "not-signed-up-yet@example.com").status_code == 201

    refused = _invite(client, owner, workspace, make_user()["email"])
    assert refused.status_code == 402
    assert "3 invites still waiting" in refused.json()["detail"]


def test_cancelling_an_invite_frees_its_seat(client, make_user):
    owner = make_user()
    workspace = _workspace(client, owner)
    _invite(client, owner, workspace, make_user()["email"])
    _invite(client, owner, workspace, make_user()["email"])
    waiting = _invite(client, owner, workspace, "not-signed-up-yet@example.com").json()
    assert _invite(client, owner, workspace, make_user()["email"]).status_code == 402

    cancelled = client.delete(
        f"{WORKSPACES}/{workspace['id']}/invites/{waiting['invite_id']}", headers=owner["headers"]
    )
    assert cancelled.status_code == 204
    assert _invite(client, owner, workspace, make_user()["email"]).status_code == 201


def test_an_invite_sent_before_seats_were_held_cannot_overfill_the_team(client, make_user, db_session):
    owner = make_user()
    workspace = _workspace(client, owner)
    invited = [make_user() for _ in range(FREE_SEATS + 1)]
    for user in invited:
        db_session.add(
            Membership(
                user_id=uuid.UUID(user["id"]),
                workspace_id=uuid.UUID(workspace["id"]),
                role="member",
                status="pending_acceptance",
            )
        )
    db_session.commit()

    for user in invited[:FREE_SEATS]:
        assert _accept(client, user, workspace).status_code == 200
    late = _accept(client, invited[-1], workspace)
    assert late.status_code == 402
    assert "no room" in late.json()["detail"]


def _link(client, owner, workspace):
    made = client.post(
        f"{WORKSPACES}/{workspace['id']}/share", json={"role": "member"}, headers=owner["headers"]
    )
    assert made.status_code == 201, made.text
    return made.json()


def _join(client, user, link):
    return client.post(f"{WORKSPACES}/share/{link['id']}/join", json={}, headers=user["headers"])


def _approve(client, owner, workspace, user):
    return client.post(
        f"{WORKSPACES}/{workspace['id']}/members/{user['id']}/approve", headers=owner["headers"]
    )


def test_a_join_through_a_link_is_held_to_the_limit_when_approved(client, make_user):
    owner = make_user()
    workspace = _workspace(client, owner)
    link = _link(client, owner, workspace)
    joiners = [make_user() for _ in range(FREE_SEATS + 1)]
    for user in joiners:
        assert _join(client, user, link).json()["status"] == "pending_approval"

    for user in joiners[:FREE_SEATS]:
        assert _approve(client, owner, workspace, user).status_code == 200
    assert _approve(client, owner, workspace, joiners[-1]).status_code == 402


def test_a_stranger_asking_to_join_does_not_take_a_seat(client, make_user):
    """Otherwise anyone holding a link could stop the owner inviting people."""
    owner = make_user()
    workspace = _workspace(client, owner)
    link = _link(client, owner, workspace)
    for _ in range(FREE_SEATS + 2):
        _join(client, make_user(), link)

    assert _invite(client, owner, workspace, make_user()["email"]).status_code == 201


def test_a_plan_with_no_member_limit_is_never_refused(client, make_user, db_session):
    owner = make_user()
    workspace = _workspace(client, owner)
    _on_plan(db_session, owner, "pro")

    for _ in range(FREE_SEATS + 3):
        assert _invite(client, owner, workspace, make_user()["email"]).status_code == 201


def test_the_owners_plan_decides_not_the_inviters(client, make_user, db_session):
    owner = make_user()
    workspace = _workspace(client, owner)
    admin = make_user()
    assert _invite(client, owner, workspace, admin["email"], role="admin").status_code == 201
    assert _accept(client, admin, workspace).status_code == 200
    _on_plan(db_session, admin, "enterprise")
    for _ in range(FREE_SEATS - 1):
        assert _invite(client, admin, workspace, make_user()["email"]).status_code == 201

    assert _invite(client, admin, workspace, make_user()["email"]).status_code == 402
