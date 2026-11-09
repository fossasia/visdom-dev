# Copyright 2017-present, The Visdom Authors
"""Daily invite-email rate-limit per workspace (issue #74)."""
import datetime
import uuid

from app.models import Membership, User, WorkspaceInvite, utcnow
from app.usage import DAILY_INVITE_LIMIT

WORKSPACES = "/api/v1/workspaces"


def _workspace(client, owner, slug=None):
    slug = slug or f"ws-{uuid.uuid4().hex[:8]}"
    made = client.post(
        WORKSPACES,
        json={"name": "Rate-limit lab", "slug": slug},
        headers=owner["headers"],
    )
    assert made.status_code == 201, made.text
    return made.json()


def _invite(client, admin, workspace, email, role="member"):
    return client.post(
        f"{WORKSPACES}/{workspace['id']}/members",
        json={"email": email, "role": role},
        headers=admin["headers"],
    )


def _ghost_email(n: int) -> str:
    return f"ghost-{n:04d}@rate-limit-test.example"


def _seed_invites(db_session, ws_id, count, email_func=_ghost_email, created_at=None):
    """Helper to quickly seed invite rows directly into the database."""
    created_at = created_at or utcnow()
    for n in range(count):
        db_session.add(
            WorkspaceInvite(
                workspace_id=ws_id,
                email=email_func(n),
                role="member",
                created_at=created_at,
            )
        )
    db_session.commit()


def test_daily_invite_limit_is_enforced(client, make_user, db_session):
    owner = make_user(tier="pro")
    workspace = _workspace(client, owner)
    ws_id = uuid.UUID(workspace["id"])

    _seed_invites(db_session, ws_id, DAILY_INVITE_LIMIT)

    refused = _invite(client, owner, workspace, _ghost_email(DAILY_INVITE_LIMIT))
    assert refused.status_code == 429, refused.text
    assert "24 hours" in refused.json()["detail"]


def test_daily_limit_resets_after_24_hours(client, make_user, db_session):
    owner = make_user(tier="pro")
    workspace = _workspace(client, owner)
    ws_id = uuid.UUID(workspace["id"])

    old_time = utcnow() - datetime.timedelta(hours=25)
    _seed_invites(db_session, ws_id, DAILY_INVITE_LIMIT, created_at=old_time)

    fresh = _invite(client, owner, workspace, _ghost_email(DAILY_INVITE_LIMIT))
    assert fresh.status_code == 201, fresh.text


def test_daily_limit_counts_registered_user_invites(client, make_user, db_session):
    owner = make_user(tier="pro")
    workspace = _workspace(client, owner)
    ws_id = uuid.UUID(workspace["id"])

    for _n in range(DAILY_INVITE_LIMIT):
        db_session.add(
            Membership(
                user_id=uuid.uuid4(),
                workspace_id=ws_id,
                role="member",
                status="pending_acceptance",
                created_at=utcnow(),
            )
        )
    db_session.commit()

    refused = _invite(client, owner, workspace, _ghost_email(0))
    assert refused.status_code == 429, refused.text


def test_daily_limit_is_per_workspace(client, make_user, db_session):
    owner = make_user(tier="pro")
    ws_a = _workspace(client, owner)
    ws_b = _workspace(client, owner)
    ws_a_id = uuid.UUID(ws_a["id"])

    _seed_invites(db_session, ws_a_id, DAILY_INVITE_LIMIT)

    assert _invite(client, owner, ws_a, _ghost_email(DAILY_INVITE_LIMIT)).status_code == 429
    assert _invite(client, owner, ws_b, _ghost_email(DAILY_INVITE_LIMIT)).status_code == 201


def test_limit_applies_on_all_plans(client, make_user, db_session):
    owner = make_user(tier="enterprise")
    workspace = _workspace(client, owner)
    ws_id = uuid.UUID(workspace["id"])

    _seed_invites(db_session, ws_id, DAILY_INVITE_LIMIT)

    refused = _invite(client, owner, workspace, _ghost_email(DAILY_INVITE_LIMIT))
    assert refused.status_code == 429, refused.text


def test_bypass_account_is_exempt_from_daily_limit(client, make_user, db_session):
    owner = make_user(tier="pro")
    workspace = _workspace(client, owner)

    record = db_session.query(User).filter(User.email == owner["email"]).first()
    record.bypass_limits = True
    db_session.commit()

    ws_id = uuid.UUID(workspace["id"])
    _seed_invites(db_session, ws_id, DAILY_INVITE_LIMIT)

    extra = _invite(client, owner, workspace, _ghost_email(DAILY_INVITE_LIMIT))
    assert extra.status_code == 201, extra.text


def test_the_limiting_invite_itself_is_still_accepted(client, make_user, db_session):
    owner = make_user(tier="pro")
    workspace = _workspace(client, owner)
    ws_id = uuid.UUID(workspace["id"])

    _seed_invites(db_session, ws_id, DAILY_INVITE_LIMIT - 1)

    at_cap = _invite(client, owner, workspace, _ghost_email(DAILY_INVITE_LIMIT - 1))
    assert at_cap.status_code == 201, at_cap.text

    over_cap = _invite(client, owner, workspace, _ghost_email(DAILY_INVITE_LIMIT))
    assert over_cap.status_code == 429, over_cap.text
    