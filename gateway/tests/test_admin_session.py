# Copyright 2017-present, The Visdom Authors
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from staff_accounts import create_staff
from starlette.testclient import TestClient

from app.admin import bootstrap, panel
from app.admin.panel import StaffAuth
from app.config import settings
from app.dependencies import get_db
from app.models import AdminUser, StaffGrant, User
from app.routers import auth
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
def site(db_session, monkeypatch):
    engine = db_session.get_bind().engine
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(panel, "SessionLocal", sessions)
    monkeypatch.setattr(panel, "engine", engine)
    monkeypatch.setattr(bootstrap, "SessionLocal", sessions)
    monkeypatch.setattr(settings, "ADMIN_ENABLED", True)

    app = FastAPI()
    def database():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.include_router(auth.router, prefix="/api/v1")
    panel.mount_admin(app, secret_key="test-secret-for-the-admin-session")
    with TestClient(app, follow_redirects=False) as client, sessions() as db:
        yield client, db


def login(client, email):
    response = client.post("/api/v1/auth/login", data={"username": email, "password": "dashboard-password"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_admin_bookmarks_use_the_shared_sign_in(site):
    client, _ = site
    for method in (client.get, client.post):
        assert method("/admin/login").headers["location"] == "/admin/"
    response = client.get("/admin/user/list?page=2")
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fadmin%2Fuser%2Flist%3Fpage%3D2"
    assert client.get("/admin/", headers={"X-API-KEY": "test-key"}).status_code == 303


def test_shared_login_and_logout(site):
    client, db = site
    member = create_staff(db, "staff@example.org", "support")
    token = login(client, member.email)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=headers).json()["has_staff_access"]
    assert client.get("/admin/user/list").status_code == 200
    assert client.get("/admin/admin-user/list").status_code == 403
    response = client.post("/api/v1/auth/logout?return_to_login=true")
    assert response.status_code == 303 and response.headers["location"] == "/login"
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    client.cookies.set("session_token", token)
    assert client.get("/admin/").status_code == 303


def test_an_email_match_does_not_grant_access(site):
    client, db = site
    db.add(AdminUser(email="staff@example.org", role="superadmin"))
    db.commit()
    response = client.post(
        "/api/v1/auth/register", json={"email": "staff@example.org", "password": "dashboard-password"}
    )
    assert response.status_code == 201
    token = login(client, "staff@example.org")
    assert client.get("/admin/").status_code == 403
    assert not client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["has_staff_access"]


def test_access_follows_the_current_user_and_staff_record(site):
    client, db = site
    member = create_staff(db, "staff@example.org", "superadmin")
    login(client, member.email)
    assert client.get("/admin/admin-user/list").status_code == 200
    member.role = "viewer"
    db.commit()
    assert client.get("/admin/admin-user/list").status_code == 403
    member.is_active = False
    db.commit()
    assert client.get("/admin/").status_code == 403
    member.is_active = True
    db.get(User, member.user_id).is_active = False
    db.commit()
    assert client.get("/admin/").status_code == 403


def test_dashboard_account_deletion_requires_staff_access_to_end_first(site):
    client, db = site
    member = create_staff(db, "staff@example.org", "superadmin")
    token = login(client, member.email)
    response = client.post(
        "/api/v1/auth/me/deletion",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "dashboard-password"},
    )
    assert response.status_code == 409
    assert client.get("/admin/user/list").status_code == 200


def test_linking_preserves_the_staff_record_and_grants(site):
    _, db = site
    email = "existing@example.org"
    user = User(email=email, username="existing", password_hash=get_password_hash("dashboard-password"))
    staff = AdminUser(email=email, role="admin", is_active=False)
    db.add_all([user, staff])
    db.flush()
    db.add(StaffGrant(admin_user_id=staff.id, permission="see_audit"))
    db.commit()
    with pytest.raises(SystemExit):
        bootstrap.main([email, str(uuid.uuid4())])
    bootstrap.main([email, str(user.id)])
    bootstrap.main([email, str(user.id)])
    db.refresh(staff)
    assert staff.user_id == user.id and staff.role == "admin" and not staff.is_active
    assert db.query(StaffGrant).one().admin_user_id == staff.id
