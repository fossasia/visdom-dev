# Copyright 2017-present, The Visdom Authors
"""Bypassing plan limits, for one account or for every account.

A bypass that lifted most limits would be worse than none, since the one it
missed would be found by a customer in the middle of a promotion. So every
limit a plan sets is pinned here: workspaces, API keys, team members, storage
and how long work is kept. The other half is that the plan is left alone, so
switching the bypass off puts back exactly what was there.
"""
import datetime
import uuid

from app import bypass, retention
from app.admin import roles
from app.models import User, Workspace, WorkspaceUsageHour
from app.usage import MEGABYTE

WORKSPACES = "/api/v1/workspaces"
KEYS = "/api/v1/keys"
RESOLVE = "/api/v1/visdom/resolve"
SUBSCRIPTION = "/api/v1/billing/subscription"
USAGE = "/api/v1/usage"

FREE_WORKSPACES = 1
FREE_KEYS = 2
FREE_SEATS = 3
FREE_STORAGE = 1024 * MEGABYTE


def _record(db, user):
    return db.query(User).filter(User.email == user["email"]).first()


def _bypass(db, user, on=True):
    bypass.set_for_account(db, _record(db, user), on)


def _workspace(client, owner):
    slug = f"lab-{uuid.uuid4().hex[:8]}"
    return client.post(WORKSPACES, json={"name": "Lab", "slug": slug}, headers=owner["headers"])


def _key(client, owner):
    return client.post(KEYS, json={"name": "training", "scope": "org"}, headers=owner["headers"])


def _invite(client, owner, workspace, email):
    return client.post(
        f"{WORKSPACES}/{workspace['id']}/members",
        json={"email": email, "role": "member"},
        headers=owner["headers"],
    )


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


def _storage_full(client, key, workspace):
    answer = client.post(
        RESOLVE, json={"workspace_slug": workspace["slug"]}, headers={"X-API-KEY": key}
    )
    assert answer.status_code == 200, answer.text
    return answer.json()["storage_full"]


def test_a_bypassed_account_can_make_more_workspaces_than_its_plan_allows(
    client, make_user, db_session
):
    owner = make_user()
    for _ in range(FREE_WORKSPACES):
        assert _workspace(client, owner).status_code == 201
    assert _workspace(client, owner).status_code == 402

    _bypass(db_session, owner)

    assert _workspace(client, owner).status_code == 201
    assert _workspace(client, owner).status_code == 201


def test_switching_the_bypass_off_keeps_what_was_made_and_refuses_more(
    client, make_user, db_session
):
    owner = make_user()
    assert _workspace(client, owner).status_code == 201
    _bypass(db_session, owner)
    assert _workspace(client, owner).status_code == 201

    _bypass(db_session, owner, on=False)

    assert _workspace(client, owner).status_code == 402
    assert len(client.get(WORKSPACES, headers=owner["headers"]).json()) == 2


def test_a_bypass_never_changes_the_plan(client, make_user, db_session):
    owner = make_user()
    _bypass(db_session, owner)
    assert _workspace(client, owner).status_code == 201
    assert _workspace(client, owner).status_code == 201
    _bypass(db_session, owner, on=False)

    assert _record(db_session, owner).tier == "free"


def test_the_switch_for_everyone_reaches_an_account_with_no_bypass_of_its_own(
    client, make_user, db_session
):
    owner = make_user()
    assert _workspace(client, owner).status_code == 201
    assert _workspace(client, owner).status_code == 402

    assert bypass.set_for_everyone(db_session, True, by="staff@example.com") is True

    assert _workspace(client, owner).status_code == 201
    assert _record(db_session, owner).bypass_limits is False

    assert bypass.set_for_everyone(db_session, False, by="staff@example.com") is True

    assert _workspace(client, owner).status_code == 402


def test_the_switch_for_everyone_reaches_someone_who_registers_later(
    client, make_user, db_session
):
    bypass.set_for_everyone(db_session, True)
    late = make_user()

    assert _workspace(client, late).status_code == 201
    assert _workspace(client, late).status_code == 201


def test_switching_everyone_off_leaves_an_account_bypassed_on_its_own(
    client, make_user, db_session
):
    owner = make_user()
    _bypass(db_session, owner)
    bypass.set_for_everyone(db_session, True)
    bypass.set_for_everyone(db_session, False)

    assert _workspace(client, owner).status_code == 201
    assert _workspace(client, owner).status_code == 201


def test_setting_the_switch_to_what_it_already_is_reports_no_change(db_session):
    assert bypass.for_everyone(db_session) is False
    assert bypass.set_for_everyone(db_session, False) is False
    assert bypass.set_for_everyone(db_session, True, by="staff@example.com") is True
    assert bypass.set_for_everyone(db_session, True, by="someone-else@example.com") is False
    assert bypass.standing(db_session).changed_by == "staff@example.com"


def test_a_bypassed_account_can_make_more_api_keys_than_its_plan_allows(
    client, make_user, db_session
):
    owner = make_user()
    for _ in range(FREE_KEYS):
        assert _key(client, owner).status_code == 201
    assert _key(client, owner).status_code == 402

    _bypass(db_session, owner)

    assert _key(client, owner).status_code == 201


def test_a_bypassed_owner_can_invite_past_the_plans_seats(client, make_user, db_session):
    owner = make_user()
    workspace = _workspace(client, owner).json()
    for _ in range(FREE_SEATS):
        assert _invite(client, owner, workspace, make_user()["email"]).status_code == 201
    late = make_user()
    assert _invite(client, owner, workspace, late["email"]).status_code == 402

    _bypass(db_session, owner)

    assert _invite(client, owner, workspace, late["email"]).status_code == 201
    accepted = client.post(
        f"{WORKSPACES}/{workspace['id']}/members/me/accept", headers=late["headers"]
    )
    assert accepted.status_code == 200, accepted.text


def test_the_storage_ceiling_is_lifted_while_bypassed(
    client, make_user, db_session
):
    owner = make_user()
    workspace = _workspace(client, owner).json()
    key = _key(client, owner).json()["raw_key"]
    _stored(db_session, workspace, FREE_STORAGE)
    assert _storage_full(client, key, workspace) is not None

    _bypass(db_session, owner)
    assert _storage_full(client, key, workspace) is None

    _bypass(db_session, owner, on=False)
    assert _storage_full(client, key, workspace) is not None


def test_the_storage_ceiling_is_lifted_for_a_member_writing_into_a_bypassed_owners_workspace(
    client, make_user, db_session
):
    owner = make_user()
    member = make_user()
    workspace = _workspace(client, owner).json()
    assert _invite(client, owner, workspace, member["email"]).status_code == 201
    joined = client.post(
        f"{WORKSPACES}/{workspace['id']}/members/me/accept", headers=member["headers"]
    )
    assert joined.status_code == 200, joined.text
    key = _key(client, member).json()["raw_key"]
    _stored(db_session, workspace, FREE_STORAGE)
    assert _storage_full(client, key, workspace) is not None

    _bypass(db_session, member)
    assert _storage_full(client, key, workspace) is not None

    _bypass(db_session, owner)
    assert _storage_full(client, key, workspace) is None


def test_the_billing_page_shows_no_ceilings_while_bypassed(client, make_user, db_session):
    owner = make_user()
    before = client.get(SUBSCRIPTION, headers=owner["headers"]).json()
    assert before["limits_bypassed"] is False
    assert before["usage"]["workspaces"]["limit"] == FREE_WORKSPACES

    _bypass(db_session, owner)

    shown = client.get(SUBSCRIPTION, headers=owner["headers"]).json()
    assert shown["limits_bypassed"] is True
    assert {metric["limit"] for metric in shown["usage"].values()} == {None}
    assert shown["tier"] == "free"
    assert shown["plan"]["limits"]["workspaces"] == FREE_WORKSPACES
    assert client.get(USAGE, headers=owner["headers"]).json()["workspace_storage_limit"] is None


def test_the_billing_page_says_so_when_everyone_is_bypassed(client, make_user, db_session):
    owner = make_user()
    bypass.set_for_everyone(db_session, True)

    shown = client.get(SUBSCRIPTION, headers=owner["headers"]).json()
    assert shown["limits_bypassed"] is True
    assert shown["usage"]["storage"]["limit"] is None


def test_nothing_is_removed_for_age_while_the_owner_is_bypassed(client, make_user, db_session):
    owner = make_user()
    made = _workspace(client, owner).json()
    workspace = db_session.get(Workspace, uuid.UUID(made["id"]))
    assert retention.window_for(db_session, workspace) == 7

    _bypass(db_session, owner)

    assert retention.window_for(db_session, workspace) is None
    assert retention.notice(db_session, workspace)["state"] == "forever"

    def nobody(*_asked):
        raise AssertionError("a bypassed workspace must not be swept")

    assert retention.sweep(db_session, enforce=True, ask=nobody)["visited"] == 0


def test_a_workspace_can_be_handed_to_a_bypassed_account_with_no_room_on_its_plan(
    client, make_user, db_session
):
    owner = make_user()
    heir = make_user()
    assert _workspace(client, heir).status_code == 201
    workspace = _workspace(client, owner).json()
    assert _invite(client, owner, workspace, heir["email"]).status_code == 201
    joined = client.post(
        f"{WORKSPACES}/{workspace['id']}/members/me/accept", headers=heir["headers"]
    )
    assert joined.status_code == 200, joined.text

    def hand_over():
        return client.post(
            f"{WORKSPACES}/{workspace['id']}/owner",
            json={"user_id": heir["id"]},
            headers=owner["headers"],
        )

    assert hand_over().status_code == 402

    _bypass(db_session, heir)

    assert hand_over().status_code == 200


def test_only_a_superadmin_may_bypass_limits():
    assert roles.can_bypass_limits(roles.SUPERADMIN)
    assert not roles.can_bypass_limits(roles.ADMIN)
    assert not roles.can_bypass_limits(roles.SUPPORT)
    assert not roles.can_bypass_limits("stranger")
    assert "bypass_limits" not in roles.editable_fields(roles.ADMIN, "User")
