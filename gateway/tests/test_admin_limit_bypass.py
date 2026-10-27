# Copyright 2017-present, The Visdom Authors
"""The limit bypass page and the bypass box on an account's form."""
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.admin import panel
from app.models import AdminUser
from app.security import get_password_hash


@pytest.fixture
def admin_client(db_session, monkeypatch):
    bind = db_session.get_bind()
    engine = getattr(bind, "engine", bind)
    staff_sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(panel, "SessionLocal", staff_sessions)
    monkeypatch.setattr(panel, "engine", engine)

    staff_db = staff_sessions()
    staff_db.add(
        AdminUser(
            id=uuid.uuid4(),
            email="staff@example.com",
            password_hash=get_password_hash("staffpassword"),
            role="superadmin",
            is_active=True,
        )
    )
    staff_db.commit()

    app = FastAPI()
    panel.mount_admin(app, secret_key="test-secret-for-the-admin-session")
    with TestClient(app) as client:
        signed_in = client.post(
            "/admin/login",
            data={"username": "staff@example.com", "password": "staffpassword"},
            follow_redirects=False,
        )
        assert signed_in.status_code in (302, 303), signed_in.text
        client.staff_db = staff_db
        yield client
    staff_db.close()


def _account(db, email="locked-out@example.com", password="their-own-password"):
    from app.models import User

    user = User(
        id=uuid.uuid4(),
        email=email,
        username=email.split("@")[0],
        password_hash=get_password_hash(password),
        tier="free",
    )
    db.add(user)
    db.commit()
    return user


def _user_form(user, **extra):
    form = {"id": str(user.id), "is_active": "true", "tier": user.tier or "free"}
    form.update(extra)
    return form


def _bypass_post(admin_client, **form):
    return admin_client.post("/admin/limit-bypass", data=form, follow_redirects=False)


def _sign_in_as(admin_client, role):
    email = f"{role}-bypass@example.com"
    db = admin_client.staff_db
    db.add(
        AdminUser(
            id=uuid.uuid4(),
            email=email,
            password_hash=get_password_hash("their-staff-password"),
            role=role,
            is_active=True,
        )
    )
    db.commit()
    admin_client.post("/admin/login", data={"username": email, "password": "their-staff-password"})


def test_bypassing_limits_for_everyone_is_recorded_and_said_on_every_page(admin_client):
    from app import bypass
    from app.models import AdminAction

    db = admin_client.staff_db
    assert "Limits bypassed" not in admin_client.get("/admin/").text
    assert 'class="ap-env is-bypass"' not in admin_client.get("/admin/user/list").text

    done = _bypass_post(admin_client, intent="everyone_on")
    assert "notice_kind=success" in done.headers["location"]

    assert bypass.for_everyone(db) is True
    switch = bypass.standing(db)
    assert switch.changed_by == "staff@example.com"
    trail = db.query(AdminAction).filter(AdminAction.model == "PlatformSwitch").one()
    assert trail.changes == {"is_on": True}
    assert trail.admin_email == "staff@example.com"
    assert 'data-everyone="on"' in admin_client.get("/admin/limit-bypass").text
    assert 'class="ap-env is-bypass"' in admin_client.get("/admin/user/list").text


def test_switching_everyone_off_again_is_recorded_too(admin_client):
    from app import bypass
    from app.models import AdminAction

    db = admin_client.staff_db
    _bypass_post(admin_client, intent="everyone_on")

    done = _bypass_post(admin_client, intent="everyone_off")
    assert "notice_kind=success" in done.headers["location"]

    db.expire_all()
    assert bypass.for_everyone(db) is False
    changes = [
        entry.changes
        for entry in db.query(AdminAction)
        .filter(AdminAction.model == "PlatformSwitch")
        .order_by(AdminAction.created_at)
    ]
    assert changes == [{"is_on": True}, {"is_on": False}]
    assert 'data-everyone="off"' in admin_client.get("/admin/limit-bypass").text


def test_switching_on_what_is_already_on_writes_no_second_entry(admin_client):
    from app.models import AdminAction

    db = admin_client.staff_db
    _bypass_post(admin_client, intent="everyone_on")

    again = _bypass_post(admin_client, intent="everyone_on")
    assert "notice_kind=info" in again.headers["location"]
    assert db.query(AdminAction).filter(AdminAction.model == "PlatformSwitch").count() == 1


def test_one_account_is_bypassed_by_its_email_and_stopped_from_the_list(admin_client):
    from app.models import AdminAction, User

    db = admin_client.staff_db
    user = _account(db, email="needs-room@example.com")
    other = _account(db, email="left-alone@example.com")

    done = _bypass_post(admin_client, intent="account_on", email="  Needs-Room@Example.com ")
    assert "notice_kind=success" in done.headers["location"]

    db.expire_all()
    assert db.get(User, user.id).bypass_limits is True
    assert db.get(User, other.id).bypass_limits is False
    assert db.get(User, user.id).tier == "free"
    trail = db.query(AdminAction).filter(AdminAction.row_id == str(user.id)).one()
    assert trail.changes == {"bypass_limits": True}
    page = admin_client.get("/admin/limit-bypass").text
    assert "needs-room@example.com" in page
    assert "left-alone@example.com" not in page

    stopped = _bypass_post(admin_client, intent="account_off", user_id=str(user.id))
    assert "notice_kind=success" in stopped.headers["location"]

    db.expire_all()
    assert db.get(User, user.id).bypass_limits is False
    assert "No account is bypassed on its own." in admin_client.get("/admin/limit-bypass").text


def test_an_email_that_matches_no_account_bypasses_nobody(admin_client):
    from app.models import AdminAction, User

    db = admin_client.staff_db
    _account(db, email="someone-real@example.com")

    done = _bypass_post(admin_client, intent="account_on", email="nobody@example.com")
    assert "notice_kind=error" in done.headers["location"]

    assert db.query(User).filter(User.bypass_limits.is_(True)).count() == 0
    assert db.query(AdminAction).count() == 0


def test_the_account_form_bypasses_one_account(admin_client):
    from app.models import User

    db = admin_client.staff_db
    user = _account(db, email="from-the-form@example.com")

    saved = admin_client.post(
        f"/admin/user/edit/{user.id}",
        data=_user_form(user, bypass_limits="y"),
        follow_redirects=False,
    )
    assert saved.status_code in (302, 303), saved.text

    db.expire_all()
    assert db.get(User, user.id).bypass_limits is True


@pytest.mark.parametrize("role", ["admin", "support"])
def test_only_a_superadmin_reaches_the_limit_bypass_page(admin_client, role):
    from app import bypass
    from app.models import User

    db = admin_client.staff_db
    user = _account(db, email="not-for-them@example.com")
    _sign_in_as(admin_client, role)

    assert admin_client.get("/admin/limit-bypass").status_code == 403
    assert _bypass_post(admin_client, intent="everyone_on").status_code == 403
    assert _bypass_post(admin_client, intent="account_on", email=user.email).status_code == 403
    assert "Limit bypass" not in admin_client.get("/admin/").text

    db.expire_all()
    assert bypass.for_everyone(db) is False
    assert db.get(User, user.id).bypass_limits is False


@pytest.mark.parametrize("role", ["admin", "support"])
def test_only_a_superadmin_can_tick_the_bypass_on_an_account(admin_client, role):
    from app.models import User

    db = admin_client.staff_db
    user = _account(db, email="form-refused@example.com")
    _sign_in_as(admin_client, role)

    refused = admin_client.post(
        f"/admin/user/edit/{user.id}",
        data=_user_form(user, bypass_limits="y"),
        follow_redirects=False,
    )
    assert refused.status_code not in (302, 303)

    db.expire_all()
    assert db.get(User, user.id).bypass_limits is False


def test_another_role_saving_a_bypassed_account_leaves_the_bypass_alone(admin_client):
    from app.models import User

    db = admin_client.staff_db
    user = _account(db, email="already-bypassed@example.com")
    user.bypass_limits = True
    db.commit()
    _sign_in_as(admin_client, "admin")

    saved = admin_client.post(
        f"/admin/user/edit/{user.id}",
        data=_user_form(user, tier="pro", bypass_limits="y"),
        follow_redirects=False,
    )
    assert saved.status_code in (302, 303), saved.text

    db.expire_all()
    changed = db.get(User, user.id)
    assert changed.tier == "pro"
    assert changed.bypass_limits is True


def test_staff_who_cannot_switch_it_are_still_told_it_is_on(admin_client):
    _bypass_post(admin_client, intent="everyone_on")
    _sign_in_as(admin_client, "support")

    page = admin_client.get("/admin/user/list").text
    assert 'class="ap-env is-bypass"' in page
    assert "/admin/limit-bypass" not in page
