# Copyright 2017-present, The Visdom Authors
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.admin import panel
from app.admin.panel import StaffAuth
from app.config import settings
from app.models import AdminUser
from app.security import get_password_hash


@pytest.mark.parametrize("secure", [True, False])
def test_the_staff_cookie_follows_the_secure_cookie_setting(monkeypatch, secure):
    monkeypatch.setattr(settings, "COOKIE_SECURE", secure)
    backend = StaffAuth(secret_key="not-a-real-secret")
    assert backend.middlewares[0].kwargs["https_only"] is secure


def test_the_staff_cookie_stays_on_the_admin_path():
    backend = StaffAuth(secret_key="not-a-real-secret")
    assert backend.middlewares[0].kwargs["path"] == "/admin"


@pytest.fixture
def sign_in(db_session, monkeypatch):
    bind = db_session.get_bind()
    engine = getattr(bind, "engine", bind)
    staff_sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(panel, "SessionLocal", staff_sessions)
    monkeypatch.setattr(panel, "engine", engine)

    staff_db = staff_sessions()
    for email, active in (("staff@example.com", True), ("left@example.com", False)):
        staff_db.add(
            AdminUser(
                id=uuid.uuid4(),
                email=email,
                password_hash=get_password_hash("staffpassword"),
                role="support",
                is_active=active,
            )
        )
    staff_db.commit()
    staff_db.close()

    checked = []
    verify = panel.verify_password

    def counting(plain, hashed):
        checked.append(hashed)
        return verify(plain, hashed)

    monkeypatch.setattr(panel, "verify_password", counting)

    app = FastAPI()
    panel.mount_admin(app, secret_key="test-secret-for-the-admin-session")
    with TestClient(app) as client:

        def attempt(email, password):
            answer = client.post(
                "/admin/login",
                data={"username": email, "password": password},
                follow_redirects=False,
            )
            return answer.status_code in (302, 303)

        attempt.checked = checked
        yield attempt


def test_the_right_password_signs_a_staff_member_in(sign_in):
    assert sign_in("staff@example.com", "staffpassword")


@pytest.mark.parametrize(
    "email, password",
    [
        ("staff@example.com", "wrongpassword"),
        ("nobody@example.com", "staffpassword"),
        ("left@example.com", "staffpassword"),
    ],
)
def test_every_refused_sign_in_checks_one_password(sign_in, email, password):
    assert not sign_in(email, password)
    assert len(sign_in.checked) == 1
