# Copyright 2017-present, The Visdom Authors
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.admin import panel
from app.models import AdminUser, SharedLink, Workspace
from app.security import get_password_hash


@pytest.fixture
def staff(db_session, monkeypatch):
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
    workspace = Workspace(id=uuid.uuid4(), name="Shared", slug="shared-links-page")
    link = SharedLink(id=uuid.uuid4(), workspace_id=workspace.id, role="member")
    staff_db.add_all([workspace, link])
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
        client.link_id = str(link.id)
        yield client
    staff_db.close()


def test_the_join_token_is_not_on_any_staff_page(staff):
    for page in ("/admin/", "/admin/workspace/list", "/admin/membership/list"):
        answer = staff.get(page)
        assert answer.status_code == 200, page
        assert staff.link_id not in answer.text, page


def test_shared_links_have_no_staff_page(staff):
    assert staff.get("/admin/shared-link/list").status_code == 404
    assert staff.get(f"/admin/shared-link/details/{staff.link_id}").status_code == 404
