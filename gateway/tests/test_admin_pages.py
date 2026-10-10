# Copyright 2017-present, The Visdom Authors
"""The staff panel's pages render.

The panel is templates plus formatters, and neither is exercised by the rest of
the suite: a template that does not parse, or a formatter that raises on a row
it was not expecting, ships and is found by whoever opens the page. These are
deliberately shallow. They ask for each page and check it came back.
"""
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.admin import panel
from app.models import AdminUser, APIKey, Membership, User, Workspace
from app.security import get_password_hash

PAGES = [
    ("/admin/", "the overview"),
    ("/admin/user/list", "users"),
    ("/admin/workspace/list", "workspaces"),
    ("/admin/membership/list", "memberships"),
    ("/admin/api-key/list", "api keys"),
    ("/admin/workspace-invite/list", "invites"),
    ("/admin/admin-user/list", "staff accounts"),
    ("/admin/admin-action/list", "the audit trail"),
    ("/admin/janitor", "the cleanup page"),
]


@pytest.fixture
def staff_panel(db_session, monkeypatch):
    bind = db_session.get_bind()
    engine = getattr(bind, "engine", bind)
    staff_sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(panel, "SessionLocal", staff_sessions)
    monkeypatch.setattr(panel, "engine", engine)

    staff_db = staff_sessions()
    for email, role in (("staff@example.com", "superadmin"), ("viewer@example.com", "viewer")):
        staff_db.add(
            AdminUser(
                id=uuid.uuid4(),
                email=email,
                password_hash=get_password_hash("staffpassword"),
                role=role,
                is_active=True,
            )
        )
    owner = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        username="owner",
        password_hash=get_password_hash("ownerpassword"),
    )
    workspace = Workspace(id=uuid.uuid4(), name="Vision", slug="vision", created_by=owner.id)
    staff_db.add_all(
        [
            owner,
            workspace,
            Membership(user_id=owner.id, workspace_id=workspace.id, role="admin"),
            APIKey(
                id=uuid.uuid4(),
                user_id=owner.id,
                name="laptop",
                prefix="visdom_live",
                hashed_key="not-a-real-hash",
            ),
        ]
    )
    staff_db.commit()

    app = FastAPI()
    panel.mount_admin(app, secret_key="test-secret-for-the-admin-session")
    with TestClient(app) as client:

        def sign_in(email):
            answer = client.post(
                "/admin/login",
                data={"username": email, "password": "staffpassword"},
                follow_redirects=False,
            )
            assert answer.status_code in (302, 303), answer.text
            return client

        sign_in.workspace_id = workspace.id
        sign_in.owner_id = owner.id
        yield sign_in
    staff_db.close()


@pytest.mark.parametrize("path,what", PAGES)
def test_every_staff_page_renders(staff_panel, path, what):
    response = staff_panel("staff@example.com").get(path, follow_redirects=False)
    assert response.status_code == 200, f"{what} at {path}: {response.status_code}"
    assert response.text.strip(), f"{what} rendered nothing"


def test_the_detail_pages_render(staff_panel):
    client = staff_panel("staff@example.com")
    for path in (
        f"/admin/workspace/details/{staff_panel.workspace_id}",
        f"/admin/user/details/{staff_panel.owner_id}",
    ):
        assert client.get(path, follow_redirects=False).status_code == 200, path


def test_a_viewer_is_not_served_the_cleanup_page(staff_panel):
    response = staff_panel("viewer@example.com").get("/admin/janitor", follow_redirects=False)
    assert response.status_code == 403
