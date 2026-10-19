# Copyright 2017-present, The Visdom Authors
"""What staff can do from the console: suspend, manage memberships and staff
accounts, set a password, hand out permissions, and read the audit trail."""
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.admin import panel
from app.models import AdminUser, Workspace
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
    ("/admin/permissions", "the permissions page"),
]


@pytest.fixture
def admin_client(db_session, monkeypatch):
    """A signed-in superadmin, and a session whose writes the panel can see.

    The engine comes from the session fixture rather than by importing conftest,
    which under pytest would load a second copy of that module with its own
    in-memory database and none of the tables in it.

    Rows for these tests are written through ``staff_db`` and committed, because
    sqladmin opens its own sessions and cannot see anything still sitting in the
    fixture's transaction.
    """
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


@pytest.mark.parametrize("path,what", PAGES)
def test_every_admin_page_renders(admin_client, path, what):
    response = admin_client.get(path, follow_redirects=False)
    assert response.status_code == 200, f"{what} at {path}: {response.status_code}"
    assert response.text.strip(), f"{what} rendered nothing"


def test_the_workspace_pages_render_with_a_workspace_in_every_standing(admin_client):
    db = admin_client.staff_db
    ordinary = Workspace(id=uuid.uuid4(), name="Ordinary", slug="ordinary")
    db.add_all(
        [
            ordinary,
            Workspace(id=uuid.uuid4(), name="Stopped", slug="stopped", is_active=False),
        ]
    )
    db.commit()

    listing = admin_client.get("/admin/workspace/list", follow_redirects=False)
    assert listing.status_code == 200
    assert "suspended" in listing.text

    detail = admin_client.get(
        f"/admin/workspace/details/{ordinary.id}", follow_redirects=False
    )
    assert detail.status_code == 200


def test_the_audit_trail_names_what_was_changed(admin_client):
    """A bare row id says a workspace was suspended without saying which one."""
    from app.models import AdminAction

    db = admin_client.staff_db
    workspace = Workspace(id=uuid.uuid4(), name="Named", slug="named-one")
    db.add(workspace)
    db.add(
        AdminAction(
            id=uuid.uuid4(),
            admin_email="staff@example.com",
            action="edit",
            model="Workspace",
            row_id=str(workspace.id),
            changes={"is_active": False},
        )
    )
    db.commit()

    trail = admin_client.get("/admin/admin-action/list", follow_redirects=False)
    assert trail.status_code == 200
    assert "named-one" in trail.text


def test_the_audit_trail_still_renders_once_the_row_is_gone(admin_client):
    """An entry outlives what it describes, which is the point of keeping one."""
    from app.models import AdminAction

    db = admin_client.staff_db
    db.add(
        AdminAction(
            id=uuid.uuid4(),
            admin_email="staff@example.com",
            action="update",
            model="User",
            row_id=str(uuid.uuid4()),
            changes={"is_active": False, "email": "long-gone@example.com"},
        )
    )
    db.commit()

    trail = admin_client.get("/admin/admin-action/list", follow_redirects=False)
    assert trail.status_code == 200
    assert "Suspended account long-gone@example.com (deleted)." in trail.text


def test_the_audit_trail_names_a_whole_page_in_a_fixed_number_of_queries(admin_client):
    from sqlalchemy import event

    from app.models import AdminAction, APIKey, Membership

    db = admin_client.staff_db
    engine = db.get_bind()

    def add_entries(count, start):
        for index in range(start, start + count):
            user = _account(db, email=f"named-{index}@example.com")
            workspace = Workspace(id=uuid.uuid4(), name=f"Space {index}", slug=f"space-{index}")
            key = APIKey(
                id=uuid.uuid4(), name=f"key-{index}", prefix="vd_", hashed_key=f"hash-{index}", user_id=user.id
            )
            db.add_all([workspace, key])
            db.flush()
            db.add(Membership(user_id=user.id, workspace_id=workspace.id, role="member"))
            for model, row_id in (
                ("User", str(user.id)),
                ("Workspace", str(workspace.id)),
                ("APIKey", str(key.id)),
                ("Membership", f"{user.id};{workspace.id}"),
            ):
                db.add(
                    AdminAction(
                        id=uuid.uuid4(),
                        admin_email="staff@example.com",
                        action="update",
                        model=model,
                        row_id=row_id,
                        changes={"is_active": False},
                    )
                )
        db.commit()

    def render():
        statements = []

        def listener(*args):
            statements.append(args[2])

        event.listen(engine, "before_cursor_execute", listener)
        try:
            page = admin_client.get("/admin/admin-action/list")
        finally:
            event.remove(engine, "before_cursor_execute", listener)
        assert page.status_code == 200
        return page.text, len(statements)

    add_entries(2, 0)
    text, few = render()
    for name in ("named-0@example.com", "space-1", "key-0 (named-0@example.com)", "named-1@example.com in space-1"):
        assert name in text

    add_entries(8, 2)
    text, many = render()
    assert "named-9@example.com in space-9" in text
    assert "key-7 (named-7@example.com)" in text
    assert many == few


def test_an_edit_records_only_what_changed_and_reads_as_a_sentence(admin_client):
    from app.models import AdminAction

    db = admin_client.staff_db
    user = _account(db, email="audited-edit@example.com")
    form = _user_form(user)
    form.pop("is_active")

    saved = admin_client.post(f"/admin/user/edit/{user.id}", data=form, follow_redirects=False)
    assert saved.status_code in (302, 303), saved.text

    entry = db.query(AdminAction).filter(AdminAction.row_id == str(user.id)).one()
    assert entry.changes == {"is_active": False, "was": {"is_active": True}}
    assert entry.admin_email == "staff@example.com"

    trail = admin_client.get("/admin/admin-action/list").text
    assert "Suspended account audited-edit@example.com." in trail
    assert "&#34;is_active&#34;" not in trail and '"is_active"' not in trail


def test_an_edit_that_changes_nothing_is_not_recorded(admin_client):
    from app.models import AdminAction

    db = admin_client.staff_db
    user = _account(db, email="untouched-edit@example.com")

    admin_client.post(f"/admin/user/edit/{user.id}", data=_user_form(user), follow_redirects=False)

    assert db.query(AdminAction).filter(AdminAction.row_id == str(user.id)).count() == 0


def test_an_entry_with_no_staff_member_says_automatic(admin_client):
    from app.models import AdminAction

    db = admin_client.staff_db
    db.add(
        AdminAction(
            id=uuid.uuid4(),
            action="update",
            model="APIKey",
            row_id=str(uuid.uuid4()),
            changes={"is_active": False},
        )
    )
    db.commit()

    trail = admin_client.get("/admin/admin-action/list").text
    assert "automatic" in trail
    assert "Revoked API key" in trail


@pytest.mark.parametrize("role", ["admin", "support"])
def test_only_a_superadmin_opens_the_audit_trail(admin_client, role):
    db = admin_client.staff_db
    db.add(
        AdminUser(
            id=uuid.uuid4(),
            email=f"{role}-audit@example.com",
            password_hash=get_password_hash("their-staff-password"),
            role=role,
            is_active=True,
        )
    )
    db.commit()
    admin_client.post(
        "/admin/login", data={"username": f"{role}-audit@example.com", "password": "their-staff-password"}
    )

    assert admin_client.get("/admin/admin-action/list", follow_redirects=False).status_code == 403
    assert "Audit trail" not in admin_client.get("/admin/").text


def test_suspending_a_workspace_through_the_form_actually_saves(admin_client):
    """The write path, not just the page it is reached from.

    Every other test here asks for a page and checks it came back, which a
    broken save survives untouched: the form renders, the POST fails, and the
    only sign is an error banner nobody automated. sqladmin runs
    ``on_model_change`` through ``anyio.from_thread``, so a dependency that
    moves that attribute takes out every edit in the console at once while
    leaving all ten pages returning 200.
    """
    workspace = Workspace(id=uuid.uuid4(), name="Noisy", slug="noisy-one", is_active=True)
    admin_client.staff_db.add(workspace)
    admin_client.staff_db.commit()

    saved = admin_client.post(
        f"/admin/workspace/edit/{workspace.id}",
        data={"is_active": "false"},
        follow_redirects=False,
    )
    assert saved.status_code in (302, 303), saved.text

    admin_client.staff_db.expire_all()
    assert admin_client.staff_db.get(Workspace, workspace.id).is_active is False


def _account(db, email="locked-out@example.com", password="their-own-password"):
    from app.models import User
    from app.security import get_password_hash

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


def test_a_superadmin_can_set_a_password_for_a_locked_out_account(admin_client):
    from app.models import User
    from app.security import verify_password

    db = admin_client.staff_db
    user = _account(db)
    before = user.token_version or 0

    saved = admin_client.post(
        f"/admin/user/edit/{user.id}",
        data=_user_form(user, password_hash="a-long-enough-password"),
        follow_redirects=False,
    )
    assert saved.status_code in (302, 303), saved.text

    db.expire_all()
    changed = db.get(User, user.id)
    assert verify_password("a-long-enough-password", changed.password_hash)
    assert changed.token_version == before + 1


def test_the_password_is_kept_exactly_as_typed(admin_client):
    from app.models import User
    from app.security import verify_password

    db = admin_client.staff_db
    user = _account(db)
    padded = "abc" + " " * 9

    admin_client.post(
        f"/admin/user/edit/{user.id}",
        data=_user_form(user, password_hash=padded),
        follow_redirects=False,
    )

    db.expire_all()
    changed = db.get(User, user.id)
    assert verify_password(padded, changed.password_hash)
    assert not verify_password("abc", changed.password_hash)


def test_an_ordinary_save_leaves_the_password_alone(admin_client):
    """The field is optional, so suspending an account must not demand one."""
    from app.models import User
    from app.security import verify_password

    db = admin_client.staff_db
    user = _account(db, email="still-mine@example.com")

    saved = admin_client.post(
        f"/admin/user/edit/{user.id}",
        data=_user_form(user, is_active="false", password_hash=""),
        follow_redirects=False,
    )
    assert saved.status_code in (302, 303), saved.text

    db.expire_all()
    kept = db.get(User, user.id)
    assert kept.is_active is False
    assert verify_password("their-own-password", kept.password_hash)
    assert (kept.token_version or 0) == 0


def test_the_form_never_carries_the_current_hash(admin_client):
    db = admin_client.staff_db
    user = _account(db, email="no-leak@example.com")

    page = admin_client.get(f"/admin/user/edit/{user.id}").text
    assert user.password_hash not in page
    assert 'id="password_hash"' in page


def test_support_cannot_set_a_password(admin_client):
    from app.models import User
    from app.security import verify_password

    db = admin_client.staff_db
    user = _account(db, email="not-yours@example.com")
    db.add(
        AdminUser(
            id=uuid.uuid4(),
            email="support-pw@example.com",
            password_hash=get_password_hash("supportpassword"),
            role="support",
            is_active=True,
        )
    )
    db.commit()
    admin_client.post(
        "/admin/login", data={"username": "support-pw@example.com", "password": "supportpassword"}
    )

    refused = admin_client.post(
        f"/admin/user/edit/{user.id}",
        data=_user_form(user, password_hash="a-long-enough-password"),
        follow_redirects=False,
    )
    assert refused.status_code not in (302, 303)

    db.expire_all()
    assert verify_password("their-own-password", db.get(User, user.id).password_hash)


def _staff_form(email, role="support", password="a-long-enough-password"):
    return {"email": email, "role": role, "password_hash": password}


def test_a_superadmin_can_add_a_staff_account(admin_client):
    """The reason this exists: adding a colleague without a shell on the box."""
    from app.models import AdminUser

    made = admin_client.post(
        "/admin/admin-user/create",
        data=_staff_form("new-colleague@example.com"),
        follow_redirects=False,
    )
    assert made.status_code in (302, 303), made.text

    admin_client.staff_db.expire_all()
    added = (
        admin_client.staff_db.query(AdminUser)
        .filter(AdminUser.email == "new-colleague@example.com")
        .first()
    )
    assert added is not None
    assert added.role == "support"


def test_the_password_is_stored_hashed_and_works(admin_client):
    """A stored plaintext password would be readable by anyone with the panel."""
    from app.models import AdminUser
    from app.security import verify_password

    admin_client.post(
        "/admin/admin-user/create",
        data=_staff_form("hashed@example.com", password="correct-horse-battery"),
        follow_redirects=False,
    )

    admin_client.staff_db.expire_all()
    added = (
        admin_client.staff_db.query(AdminUser)
        .filter(AdminUser.email == "hashed@example.com")
        .first()
    )
    assert added is not None
    assert added.password_hash != "correct-horse-battery"
    assert verify_password("correct-horse-battery", added.password_hash)


def test_a_short_password_is_refused(admin_client):
    """Twelve characters, the same floor the bootstrap script enforces."""
    from app.models import AdminUser

    refused = admin_client.post(
        "/admin/admin-user/create",
        data=_staff_form("tooshort@example.com", password="short"),
        follow_redirects=False,
    )
    assert refused.status_code not in (302, 303)

    admin_client.staff_db.expire_all()
    assert (
        admin_client.staff_db.query(AdminUser)
        .filter(AdminUser.email == "tooshort@example.com")
        .first()
        is None
    )


def test_an_unknown_role_is_refused(admin_client):
    """The role decides what the account can read, so it is not free text."""
    from app.models import AdminUser

    refused = admin_client.post(
        "/admin/admin-user/create",
        data=_staff_form("badrole@example.com", role="root"),
        follow_redirects=False,
    )
    assert refused.status_code not in (302, 303)

    admin_client.staff_db.expire_all()
    assert (
        admin_client.staff_db.query(AdminUser)
        .filter(AdminUser.email == "badrole@example.com")
        .first()
        is None
    )


def test_the_audit_trail_does_not_keep_the_password(admin_client):
    """Recording who added an account is useful. Recording the password they
    chose is a second place to steal it from, and it outlives the account."""
    from app.models import AdminAction

    admin_client.post(
        "/admin/admin-user/create",
        data=_staff_form("audited@example.com", password="a-memorable-secret"),
        follow_redirects=False,
    )

    admin_client.staff_db.expire_all()
    rows = admin_client.staff_db.query(AdminAction).all()
    assert rows, "the creation should have been recorded at all"
    for row in rows:
        assert "a-memorable-secret" not in str(row.changes)


def test_a_staff_account_can_be_stopped(admin_client):
    """Removing someone's access should not need a shell on the box either."""
    from app.models import AdminUser

    admin_client.post(
        "/admin/admin-user/create",
        data=_staff_form("leaver@example.com"),
        follow_redirects=False,
    )
    admin_client.staff_db.expire_all()
    leaver = (
        admin_client.staff_db.query(AdminUser)
        .filter(AdminUser.email == "leaver@example.com")
        .first()
    )
    assert leaver is not None and leaver.is_active

    stopped = admin_client.post(
        f"/admin/admin-user/edit/{leaver.id}", data={}, follow_redirects=False
    )
    assert stopped.status_code in (302, 303), stopped.text

    admin_client.staff_db.expire_all()
    assert admin_client.staff_db.get(AdminUser, leaver.id).is_active is False


def test_the_last_superadmin_cannot_be_stopped(admin_client):
    """A console that can lock everyone out of itself is recovered with a shell
    on the box, which is the thing this view exists to avoid."""
    from app.models import AdminUser

    only = (
        admin_client.staff_db.query(AdminUser)
        .filter(AdminUser.role == "superadmin", AdminUser.is_active.is_(True))
        .all()
    )
    assert len(only) == 1, "the fixture should sign in the only superadmin"

    refused = admin_client.post(
        f"/admin/admin-user/edit/{only[0].id}", data={}, follow_redirects=False
    )
    assert refused.status_code not in (302, 303)

    admin_client.staff_db.expire_all()
    assert admin_client.staff_db.get(AdminUser, only[0].id).is_active is True


def test_editing_a_staff_account_cannot_change_the_role(admin_client):
    """Changing what a colleague may see is a different decision from taking
    their access away, and the edit form is only for the second."""
    from app.models import AdminUser

    admin_client.post(
        "/admin/admin-user/create",
        data=_staff_form("support-only@example.com", role="support"),
        follow_redirects=False,
    )
    admin_client.staff_db.expire_all()
    account = (
        admin_client.staff_db.query(AdminUser)
        .filter(AdminUser.email == "support-only@example.com")
        .first()
    )
    assert account is not None

    admin_client.post(
        f"/admin/admin-user/edit/{account.id}",
        data={"is_active": "y", "role": "superadmin"},
        follow_redirects=False,
    )

    admin_client.staff_db.expire_all()
    assert admin_client.staff_db.get(AdminUser, account.id).role == "support"


def _flashes(page):
    import json
    import re

    found = re.search(r'<script type="application/json" id="ap-flash">(.*?)</script>', page, re.S)
    assert found, "the page carries no notifications block"
    return json.loads(found.group(1))


def test_an_action_reports_back_as_a_notification_of_its_kind(admin_client):
    done = admin_client.post("/admin/permissions", data={}, follow_redirects=False)
    assert "notice_kind=info" in done.headers["location"]

    page = admin_client.get(done.headers["location"]).text
    assert _flashes(page) == [{"kind": "info", "message": "Nothing was changed."}]


def test_a_notice_cannot_break_out_of_the_notifications_block(admin_client):
    sneaky = "</script><script>alert(1)</script>"
    page = admin_client.get("/admin/janitor", params={"notice": sneaky, "notice_kind": "success"}).text
    assert "<script>alert(1)" not in page
    assert _flashes(page) == [{"kind": "success", "message": sneaky}]


def test_a_page_with_nothing_to_report_shows_no_notification(admin_client):
    assert _flashes(admin_client.get("/admin/janitor").text) == []


def test_no_admin_page_falls_back_to_the_browsers_own_dialogs():
    import pathlib
    import re

    templates = pathlib.Path(panel.__file__).parent / "templates"
    for template in templates.rglob("*.html"):
        text = template.read_text()
        assert not re.search(r"(?<![\w.])confirm\(", text), template.name
        assert not re.search(r"\son(?:click|submit|change)=", text), template.name


def test_deleting_a_row_asks_in_the_consoles_own_dialog(admin_client):
    page = admin_client.get("/admin/membership/list").text
    assert 'class="modal-content ap-confirm"' in page
    assert 'id="modal-delete-button"' in page


def _nav(page_html):
    import re

    return {
        text.strip(): (href, "is-active" in cls)
        for cls, href, text in re.findall(
            r'<a class="ap-nav-row([^"]*)" href="([^"]+)">.*?<span[^>]*>([^<]+)</span>',
            page_html,
            re.S,
        )
    }


def test_each_custom_page_has_its_own_sidebar_link(admin_client):
    """Two custom views with the same exposed method name share a route name,
    so one link opens the other page."""
    nav = _nav(admin_client.get("/admin/janitor").text)
    assert nav["Permissions"][0].endswith("/admin/permissions")
    assert nav["Cleanup"][0].endswith("/admin/janitor")


def test_only_the_page_you_are_on_is_selected(admin_client):
    for path, selected in (("/admin/janitor", "Cleanup"), ("/admin/permissions", "Permissions")):
        nav = _nav(admin_client.get(path).text)
        active = [name for name, (_href, on) in nav.items() if on]
        assert active == [selected], (path, active)


def _staff(db, email, role):
    member = AdminUser(
        id=uuid.uuid4(),
        email=email,
        password_hash=get_password_hash("their-staff-password"),
        role=role,
        is_active=True,
    )
    db.add(member)
    db.commit()
    return member


def _sign_in(admin_client, email, password="their-staff-password"):
    admin_client.post("/admin/login", data={"username": email, "password": password})


def _grant(admin_client, group=(), single=()):
    form = {"group": list(group), "single": [f"{permission}|{member.id}" for permission, member in single]}
    return admin_client.post("/admin/permissions", data=form, follow_redirects=False)


def test_a_grant_to_every_admin_opens_the_audit_trail_to_them(admin_client):
    db = admin_client.staff_db
    _staff(db, "group-admin@example.com", "admin")

    saved = _grant(admin_client, group=["see_audit"])
    assert "Saved+1+change" in saved.headers["location"]

    _sign_in(admin_client, "group-admin@example.com")
    assert admin_client.get("/admin/admin-action/list").status_code == 200
    assert "Gave every admin permission to see the audit trail." in admin_client.get(
        "/admin/admin-action/list"
    ).text
    assert admin_client.get("/admin/permissions").status_code == 403


def test_a_grant_to_one_admin_does_not_reach_the_others(admin_client):
    db = admin_client.staff_db
    chosen = _staff(db, "chosen-admin@example.com", "admin")
    _staff(db, "other-admin@example.com", "admin")

    _grant(admin_client, single=[("see_audit", chosen)])

    _sign_in(admin_client, "chosen-admin@example.com")
    assert admin_client.get("/admin/admin-action/list").status_code == 200
    _sign_in(admin_client, "other-admin@example.com")
    assert admin_client.get("/admin/admin-action/list", follow_redirects=False).status_code == 403


def test_taking_a_grant_back_closes_the_door_again(admin_client):
    db = admin_client.staff_db
    _staff(db, "briefly-admin@example.com", "admin")
    _grant(admin_client, group=["see_audit"])

    taken = _grant(admin_client)
    assert "Saved+1+change" in taken.headers["location"]

    trail = admin_client.get("/admin/admin-action/list").text
    assert "Took away from every admin the permission to see the audit trail." in trail
    _sign_in(admin_client, "briefly-admin@example.com")
    assert admin_client.get("/admin/admin-action/list", follow_redirects=False).status_code == 403


def test_support_cannot_be_given_anything(admin_client):
    db = admin_client.staff_db
    helper = _staff(db, "helper-support@example.com", "support")

    _grant(admin_client, group=["see_audit"], single=[("see_audit", helper)])

    page = admin_client.get("/admin/permissions").text
    assert "helper-support@example.com" not in page
    _sign_in(admin_client, "helper-support@example.com")
    assert admin_client.get("/admin/admin-action/list", follow_redirects=False).status_code == 403


def test_saving_the_same_permissions_changes_nothing(admin_client):
    from app.models import AdminAction

    db = admin_client.staff_db
    _staff(db, "steady-admin@example.com", "admin")
    _grant(admin_client, group=["see_audit"])
    before = db.query(AdminAction).count()

    again = _grant(admin_client, group=["see_audit"])
    assert "notice_kind=info" in again.headers["location"]
    assert db.query(AdminAction).count() == before


def test_an_unknown_permission_is_ignored(admin_client):
    from app.models import StaffGrant

    _grant(admin_client, group=["become_superadmin"])
    assert admin_client.staff_db.query(StaffGrant).count() == 0


def test_a_membership_role_must_be_one_the_product_knows(admin_client):
    from app.models import Membership, User

    db = admin_client.staff_db
    user = User(id=uuid.uuid4(), email="typo@example.com", username="typo", password_hash="x")
    workspace = Workspace(id=uuid.uuid4(), name="Typo", slug="typo-lab", created_by=user.id)
    membership = Membership(user_id=user.id, workspace_id=workspace.id, role="member", status="active")
    db.add_all([user, workspace, membership])
    db.commit()
    key = (membership.user_id, membership.workspace_id)

    import re

    listing = admin_client.get("/admin/membership/list").text
    edit = next(href for href in re.findall(r'href="([^"]*/membership/edit/[^"]+)"', listing) if str(user.id) in href)
    form = admin_client.get(edit).text
    assert '<select' in form and 'value="viewer"' in form

    refused = admin_client.post(
        edit, data={"role": "admn", "save": "Save"}, follow_redirects=False
    )
    assert refused.status_code == 400
    db.expire_all()
    assert db.get(Membership, key).role == "member"

    saved = admin_client.post(
        edit, data={"role": "viewer", "save": "Save"}, follow_redirects=False
    )
    assert saved.status_code in (302, 303), saved.text
    db.expire_all()
    assert db.get(Membership, key).role == "viewer"

    trail = admin_client.get("/admin/admin-action/list").text
    assert "Changed typo@example.com in typo-lab to viewer." in trail


def test_the_plan_dropdown_marks_hidden_and_archived_plans(admin_client):
    import datetime

    from app.models import Plan, User

    db = admin_client.staff_db
    db.add(Plan(id="internal", name="Internal", is_public=False, limits={}, features=[]))
    db.add(
        Plan(
            id="legacy",
            name="Legacy",
            archived_at=datetime.datetime.now(datetime.timezone.utc),
            limits={},
            features=[],
        )
    )
    user = User(id=uuid.uuid4(), email="picker@example.com", username="picker", password_hash="x")
    db.add(user)
    db.commit()

    page = admin_client.get(f"/admin/user/edit/{user.id}").text
    assert "Internal (hidden)" in page
    assert "Legacy (archived)" in page


def test_an_account_cannot_be_moved_onto_an_archived_plan(admin_client):
    import datetime

    from app.models import Plan, User

    db = admin_client.staff_db
    db.add(
        Plan(
            id="legacy",
            name="Legacy",
            archived_at=datetime.datetime.now(datetime.timezone.utc),
            limits={},
            features=[],
        )
    )
    user = User(id=uuid.uuid4(), email="mover@example.com", username="mover", password_hash="x", tier="free")
    db.add(user)
    db.commit()

    response = admin_client.post(
        f"/admin/user/edit/{user.id}", data={"is_active": "y", "tier": "legacy"}, follow_redirects=False
    )
    db.expire_all()
    assert response.status_code == 400
    assert db.get(User, user.id).tier == "free"
