# Copyright 2017-present, The Visdom Authors
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from app.models import User
from app.routers import billing as billing_router
from app.routers import workspaces as workspaces_router

BILLING = "/api/v1/billing"
WORKSPACES = "/api/v1/workspaces"


def test_list_plans(client):
    response = client.get(f"{BILLING}/plans")
    assert response.status_code == 200
    plans = response.json()
    assert [plan["id"] for plan in plans] == ["free", "pro", "enterprise"]

    free, pro, enterprise = plans
    assert free["price"] == 0
    assert free["limits"] == {
        "workspaces": 1,
        "members": 3,
        "api_keys": 2,
        "storage_mb": 1024,
        "workspace_storage_mb": 1024,
    }
    assert pro["price"] == 29
    assert pro["limits"]["members"] is None
    assert enterprise["price"] is None
    assert enterprise["limits"] == {
        "workspaces": None,
        "members": None,
        "api_keys": None,
        "storage_mb": None,
        "workspace_storage_mb": None,
    }
    assert all(plan["features"] for plan in plans)


def test_subscription_requires_auth(client):
    assert client.get(f"{BILLING}/subscription").status_code == 401
    assert client.post(f"{BILLING}/subscription", json={"tier": "pro"}).status_code == 401


def test_fresh_user_subscription(client, make_user):
    user = make_user()
    response = client.get(f"{BILLING}/subscription", headers=user["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "free"
    assert data["plan"]["id"] == "free"
    assert data["usage"] == {
        "workspaces": {"used": 0, "limit": 1},
        "members": {"used": 0, "limit": 3},
        "api_keys": {"used": 0, "limit": 2},
    }


def test_subscription_usage_counts(client, make_user, make_workspace, add_member):
    owner = make_user()
    member = make_user()
    pending = make_user()
    ws1 = make_workspace(owner)
    make_workspace(owner)
    add_member(owner, ws1, member)
    client.post(
        f"/api/v1/workspaces/{ws1['id']}/members",
        json={"email": pending["email"], "role": "member"},
        headers=owner["headers"],
    )
    client.post("/api/v1/keys", json={"name": "usage-key"}, headers=owner["headers"])

    usage = client.get(f"{BILLING}/subscription", headers=owner["headers"]).json()["usage"]
    assert usage["workspaces"]["used"] == 2
    assert usage["members"]["used"] == 2
    assert usage["api_keys"]["used"] == 1

    member_usage = client.get(f"{BILLING}/subscription", headers=member["headers"]).json()["usage"]
    assert member_usage["workspaces"]["used"] == 0
    assert member_usage["members"]["used"] == 0
    assert member_usage["api_keys"]["used"] == 0


def test_paid_plan_changes_require_a_verified_entitlement(client, make_user, db_session):
    user = make_user()

    for tier in ("pro", "enterprise"):
        response = client.post(
            f"{BILLING}/subscription", json={"tier": tier}, headers=user["headers"]
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Paid plan changes require a verified subscription."

    assert client.get(f"{BILLING}/subscription", headers=user["headers"]).json()["tier"] == "free"
    first_workspace = client.post(
        WORKSPACES,
        json={"name": "First", "slug": "first-free-workspace"},
        headers=user["headers"],
    )
    assert first_workspace.status_code == 201
    second_workspace = client.post(
        WORKSPACES,
        json={"name": "Second", "slug": "second-free-workspace"},
        headers=user["headers"],
    )
    assert second_workspace.status_code == 403

    # Simulate a paid tier granted by a trusted subscription integration.
    account = db_session.query(User).filter(User.email == user["email"]).one()
    account.tier = "pro"
    db_session.commit()
    downgraded = client.post(
        f"{BILLING}/subscription", json={"tier": "free"}, headers=user["headers"]
    )
    assert downgraded.status_code == 200
    assert downgraded.json()["tier"] == "free"
    assert client.get("/api/v1/auth/me", headers=user["headers"]).json()["tier"] == "free"


def test_workspace_creation_uses_tier_after_a_concurrent_downgrade(
    file_database_client, monkeypatch
):
    client, file_sessions = file_database_client
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "quota-downgrade@example.com", "password": "securepassword"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "quota-downgrade@example.com", "password": "securepassword"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    db = file_sessions()
    account = db.query(User).filter(User.email == "quota-downgrade@example.com").one()
    account.tier = "pro"
    db.commit()
    db.close()

    for number in range(2):
        created = client.post(
            WORKSPACES,
            json={"name": f"Existing {number}", "slug": f"existing-{number}"},
            headers=headers,
        )
        assert created.status_code == 201

    original_lock = workspaces_router.lock_user_for_workspace_quota
    downgrade_has_lock = Event()
    allow_downgrade_to_finish = Event()
    creation_is_waiting_for_lock = Event()

    def hold_downgrade_lock(db, user_id):
        user = original_lock(db, user_id)
        downgrade_has_lock.set()
        assert allow_downgrade_to_finish.wait(timeout=10)
        return user

    def signal_creation_lock(db, user_id):
        creation_is_waiting_for_lock.set()
        return original_lock(db, user_id)

    monkeypatch.setattr(billing_router, "lock_user_for_workspace_quota", hold_downgrade_lock)
    monkeypatch.setattr(workspaces_router, "lock_user_for_workspace_quota", signal_creation_lock)

    with ThreadPoolExecutor(max_workers=2) as executor:
        downgrade = executor.submit(
            client.post,
            f"{BILLING}/subscription",
            json={"tier": "free"},
            headers=headers,
        )
        assert downgrade_has_lock.wait(timeout=5)
        create = executor.submit(
            client.post,
            WORKSPACES,
            json={"name": "Must be rejected", "slug": "over-limit"},
            headers=headers,
        )
        try:
            assert creation_is_waiting_for_lock.wait(timeout=5)
        finally:
            allow_downgrade_to_finish.set()

        assert downgrade.result(timeout=10).status_code == 200
        assert create.result(timeout=10).status_code == 403


def test_change_plan_invalid_tier(client, make_user):
    user = make_user()
    response = client.post(
        f"{BILLING}/subscription", json={"tier": "platinum"}, headers=user["headers"]
    )
    assert response.status_code == 422


WORKSPACES = "/api/v1/workspaces"
KEYS = "/api/v1/keys"


def test_free_plan_refuses_a_second_workspace(client, make_user):
    user = make_user()
    first = client.post(
        WORKSPACES, json={"name": "One", "slug": "limit-one"}, headers=user["headers"]
    )
    assert first.status_code == 201

    second = client.post(
        WORKSPACES, json={"name": "Two", "slug": "limit-two"}, headers=user["headers"]
    )
    assert second.status_code == 402
    assert "workspace limit" in second.json()["detail"]


def test_upgrading_raises_the_workspace_ceiling(client, make_user):
    user = make_user()
    assert (
        client.post(
            WORKSPACES, json={"name": "One", "slug": "up-one"}, headers=user["headers"]
        ).status_code
        == 201
    )
    assert (
        client.post(
            WORKSPACES, json={"name": "Two", "slug": "up-two"}, headers=user["headers"]
        ).status_code
        == 402
    )

    client.post(f"{BILLING}/subscription", json={"tier": "pro"}, headers=user["headers"])

    assert (
        client.post(
            WORKSPACES, json={"name": "Two", "slug": "up-two"}, headers=user["headers"]
        ).status_code
        == 201
    )


def test_an_unlimited_plan_is_never_refused(client, make_user):
    user = make_user()
    client.post(
        f"{BILLING}/subscription", json={"tier": "enterprise"}, headers=user["headers"]
    )
    for n in range(3):
        created = client.post(
            WORKSPACES,
            json={"name": f"W{n}", "slug": f"unlimited-{n}"},
            headers=user["headers"],
        )
        assert created.status_code == 201, created.text


def test_free_plan_refuses_a_third_api_key(client, make_user):
    user = make_user()
    for n in range(2):
        made = client.post(
            KEYS, json={"name": f"key-{n}", "scope": "org"}, headers=user["headers"]
        )
        assert made.status_code == 201, made.text

    third = client.post(
        KEYS, json={"name": "key-3", "scope": "org"}, headers=user["headers"]
    )
    assert third.status_code == 402
    assert "API key limit" in third.json()["detail"]


def test_the_billing_page_and_the_refusal_agree(client, make_user):
    """The number someone is shown is the number they are held to."""
    user = make_user()
    client.post(
        WORKSPACES, json={"name": "One", "slug": "agree-one"}, headers=user["headers"]
    )

    shown = client.get(f"{BILLING}/subscription", headers=user["headers"]).json()
    assert shown["usage"]["workspaces"] == {"used": 1, "limit": 1}

    refused = client.post(
        WORKSPACES, json={"name": "Two", "slug": "agree-two"}, headers=user["headers"]
    )
    assert refused.status_code == 402


def _plan(db, plan_id, *, workspaces=1, members=3, api_keys=2, public=True, archived=False):
    import datetime

    from app.models import Plan

    plan = Plan(
        id=plan_id,
        name=plan_id.title(),
        price=5,
        sort_order=9,
        is_public=public,
        archived_at=datetime.datetime.now(datetime.timezone.utc) if archived else None,
        limits={"workspaces": workspaces, "members": members, "api_keys": api_keys},
        features=[],
    )
    db.add(plan)
    db.commit()
    return plan


def _put_on(db, user, tier):
    from app.models import User

    record = db.query(User).filter(User.email == user["email"]).first()
    record.tier = tier
    db.commit()


def test_a_hidden_plan_is_not_offered(client, db_session):
    _plan(db_session, "internal", public=False)
    assert "internal" not in [plan["id"] for plan in client.get(f"{BILLING}/plans").json()]


def test_an_archived_plan_is_not_offered(client, db_session):
    _plan(db_session, "legacy", archived=True)
    assert "legacy" not in [plan["id"] for plan in client.get(f"{BILLING}/plans").json()]


def test_an_account_cannot_move_itself_onto_a_hidden_plan(client, make_user, db_session):
    """Changing plan needs no payment yet, so a hidden tier must not be a
    request away."""
    _plan(db_session, "internal", workspaces=None, public=False)
    user = make_user()
    refused = client.post(f"{BILLING}/subscription", json={"tier": "internal"}, headers=user["headers"])
    assert refused.status_code == 422


def test_an_account_cannot_move_itself_onto_an_archived_plan(client, make_user, db_session):
    _plan(db_session, "legacy", archived=True)
    user = make_user()
    refused = client.post(f"{BILLING}/subscription", json={"tier": "legacy"}, headers=user["headers"])
    assert refused.status_code == 422


def test_a_new_tier_is_held_to_its_own_limits(client, make_user, db_session):
    _plan(db_session, "team", workspaces=2)
    user = make_user()
    _put_on(db_session, user, "team")

    for n in range(2):
        made = client.post(WORKSPACES, json={"name": f"T{n}", "slug": f"team-{n}"}, headers=user["headers"])
        assert made.status_code == 201, made.text
    third = client.post(WORKSPACES, json={"name": "T2", "slug": "team-2"}, headers=user["headers"])
    assert third.status_code == 402


def test_changing_a_limit_applies_at_once(client, make_user, db_session):
    """No cache stands between an edit in the console and the next request."""
    from app.models import Plan

    user = make_user()
    free = db_session.get(Plan, "free")
    free.limits = {"workspaces": 0, "members": 3, "api_keys": 2, "storage_mb": 1024}
    db_session.commit()

    refused = client.post(WORKSPACES, json={"name": "One", "slug": "at-once"}, headers=user["headers"])
    assert refused.status_code == 402


def test_an_account_on_an_archived_plan_keeps_its_limits(client, make_user, db_session):
    """Archiving stops new assignments; it does not take anything away."""
    import datetime

    from app.models import Plan

    user = make_user()
    _put_on(db_session, user, "pro")
    db_session.get(Plan, "pro").archived_at = datetime.datetime.now(datetime.timezone.utc)
    db_session.commit()

    shown = client.get(f"{BILLING}/subscription", headers=user["headers"]).json()
    assert shown["tier"] == "pro"
    assert shown["usage"]["workspaces"]["limit"] == 10


def test_limits_must_name_every_marker():
    """A missing marker would otherwise read as unlimited."""
    import pytest

    from app.billing import validate_limits

    with pytest.raises(ValueError, match="missing: api_keys"):
        validate_limits({"workspaces": 1, "members": 3})


def test_limits_refuse_an_unknown_marker():
    import pytest

    from app.billing import validate_limits

    with pytest.raises(ValueError, match="Unknown limit: workspace"):
        validate_limits({"workspace": 1, "members": 3, "api_keys": 2, "storage_mb": 1, "workspace_storage_mb": 1})


def test_limits_refuse_a_negative_or_non_whole_value():
    import pytest

    from app.billing import validate_limits

    for bad in (-1, 1.5, "3", True):
        with pytest.raises(ValueError):
            validate_limits(
                {"workspaces": bad, "members": 3, "api_keys": 2, "storage_mb": 1, "workspace_storage_mb": 1}
            )


def test_null_means_unlimited():
    from app.billing import validate_limits

    limits = {
        "workspaces": None,
        "members": 0,
        "api_keys": 5,
        "storage_mb": None,
        "workspace_storage_mb": None,
    }
    assert validate_limits(limits) == {
        "workspaces": None,
        "members": 0,
        "api_keys": 5,
        "storage_mb": None,
        "workspace_storage_mb": None,
    }


def test_an_untouched_features_box_saves_as_no_features():
    """The console pre-fills the field with an empty object, not a list."""
    from app.billing import validate_features

    assert validate_features({}) == []
    assert validate_features(None) == []
    assert validate_features(["  one  ", ""]) == ["one"]


def test_an_expired_or_revoked_key_frees_its_slot(client, make_user, db_session):
    import datetime

    from app.models import APIKey, User

    user = make_user()
    for n in range(2):
        made = client.post(KEYS, json={"name": f"old-{n}", "scope": "org"}, headers=user["headers"])
        assert made.status_code == 201, made.text

    record = db_session.query(User).filter(User.email == user["email"]).first()
    expired, revoked = db_session.query(APIKey).filter(APIKey.user_id == record.id).order_by(APIKey.name).all()
    expired.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    revoked.is_active = False
    db_session.commit()

    shown = client.get(f"{BILLING}/subscription", headers=user["headers"]).json()
    assert shown["usage"]["api_keys"] == {"used": 0, "limit": 2}
    for n in range(2):
        made = client.post(KEYS, json={"name": f"new-{n}", "scope": "org"}, headers=user["headers"])
        assert made.status_code == 201, made.text
    refused = client.post(KEYS, json={"name": "new-2", "scope": "org"}, headers=user["headers"])
    assert refused.status_code == 402


def test_a_bad_limit_in_a_stored_plan_allows_nothing(client, make_user, db_session):
    plan = _plan(db_session, "broken")
    plan.limits = {"workspaces": -1, "members": "3", "api_keys": None}
    db_session.commit()
    user = make_user()
    _put_on(db_session, user, "broken")

    shown = client.get(f"{BILLING}/subscription", headers=user["headers"]).json()
    assert shown["plan"]["limits"] == {
        "workspaces": 0,
        "members": 0,
        "api_keys": None,
        "storage_mb": 0,
        "workspace_storage_mb": 0,
    }
    refused = client.post(WORKSPACES, json={"name": "B", "slug": "broken-one"}, headers=user["headers"])
    assert refused.status_code == 402


def test_the_billing_page_counts_invites_still_waiting(client, make_user, db_session):
    _plan(db_session, "pair", members=2)
    owner = make_user()
    _put_on(db_session, owner, "pair")
    workspace = client.post(WORKSPACES, json={"name": "P", "slug": "pair-one"}, headers=owner["headers"]).json()

    def invite(email):
        return client.post(
            f"{WORKSPACES}/{workspace['id']}/members",
            json={"email": email, "role": "member"},
            headers=owner["headers"],
        )

    assert invite(make_user()["email"]).status_code == 201
    assert invite("no-account-yet@example.com").status_code == 201

    shown = client.get(f"{BILLING}/subscription", headers=owner["headers"]).json()
    assert shown["usage"]["members"] == {"used": 2, "limit": 2}
    assert invite(make_user()["email"]).status_code == 402


def test_holding_an_account_reads_its_current_plan(make_user, db_session):
    """A plan change that commits while a request waits for the lock must be
    the one its limits are checked against."""
    from sqlalchemy import update

    from app.models import User
    from app.usage import hold_account

    user = make_user()
    record = db_session.query(User).filter(User.email == user["email"]).first()
    assert record.tier == "free"
    moved = update(User).where(User.id == record.id).values(tier="pro")
    db_session.execute(moved.execution_options(synchronize_session=False))

    hold_account(db_session, record)
    assert record.tier == "pro"
