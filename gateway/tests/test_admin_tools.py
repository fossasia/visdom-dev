# Copyright 2017-present, The Visdom Authors
"""The staff panel's cleanup, plan, usage and account trash pages."""

import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.admin import panel
from app.models import AdminUser, APIKey, Membership, User, Workspace, WorkspaceInvite, utcnow
from app.security import get_password_hash


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
    from app.admin import usage_view

    monkeypatch.setattr(usage_view, "SessionLocal", staff_sessions)

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


def _instances_answer(monkeypatch, workspaces, answered=True):
    from app.admin import activity

    monkeypatch.setattr(
        activity, "activity_snapshot", lambda timeout=None: {"answered": answered, "workspaces": workspaces}
    )
    monkeypatch.setattr(activity, "_cache", {"at": 0.0, "value": {"answered": False, "workspaces": {}}})


def test_the_workspace_page_reports_the_work_a_workspace_caused(admin_client, monkeypatch):
    """The counters come from the instances, so the page is asked with a known
    answer rather than a live deployment."""

    workspace = Workspace(id=uuid.uuid4(), name="Busy", slug="busy-one")
    admin_client.staff_db.add(workspace)
    admin_client.staff_db.commit()

    _instances_answer(
        monkeypatch,
        {
            str(workspace.id): {
                "viewers": 1,
                "writers": 0,
                "writes": 12,
                "broadcasts": 30,
                "broadcast_bytes": 4096,
            }
        },
    )

    detail = admin_client.get(
        f"/admin/workspace/details/{workspace.id}", follow_redirects=False
    )
    assert detail.status_code == 200
    assert "12 writes" in detail.text
    assert "30 pushes" in detail.text
    assert "4.0 KB" in detail.text


def test_a_workspace_whose_instance_reports_no_counters_says_so(admin_client, monkeypatch):
    """A visdom without the counters should read as unknown rather than as a
    workspace that has done nothing."""

    workspace = Workspace(id=uuid.uuid4(), name="Quiet", slug="quiet-one")
    admin_client.staff_db.add(workspace)
    admin_client.staff_db.commit()

    _instances_answer(monkeypatch, {str(workspace.id): {"viewers": 0}})

    detail = admin_client.get(
        f"/admin/workspace/details/{workspace.id}", follow_redirects=False
    )
    assert detail.status_code == 200
    assert "not reported" in detail.text


def test_a_workspace_no_instance_mentions_has_never_been_written_to(
    admin_client, monkeypatch
):
    """Absent from an answer is a real answer.

    Every instance shares the env volume, so one that replies at all reports
    every workspace that has a directory. A workspace it does not mention has
    none, which means nobody has ever written to it.
    """

    workspace = Workspace(id=uuid.uuid4(), name="Fresh", slug="fresh-one")
    admin_client.staff_db.add(workspace)
    admin_client.staff_db.commit()

    _instances_answer(monkeypatch, {})

    detail = admin_client.get(
        f"/admin/workspace/details/{workspace.id}", follow_redirects=False
    )
    assert detail.status_code == 200
    assert "never" in detail.text
    assert "nothing yet" in detail.text


def test_a_workspace_stays_unknown_when_no_instance_answered(admin_client, monkeypatch):
    """Silence from every instance is not evidence that nothing has happened."""

    workspace = Workspace(id=uuid.uuid4(), name="Offline", slug="offline-one")
    admin_client.staff_db.add(workspace)
    admin_client.staff_db.commit()

    _instances_answer(monkeypatch, {}, answered=False)

    detail = admin_client.get(
        f"/admin/workspace/details/{workspace.id}", follow_redirects=False
    )
    assert detail.status_code == 200
    assert "unknown" in detail.text


def _account(db, email="locked-out@example.com", password="their-own-password"):
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


def _key(db, owner, name, *, age_days=5, used_days_ago=None):
    import datetime


    now = datetime.datetime.now(datetime.timezone.utc)
    key = APIKey(
        id=uuid.uuid4(),
        name=name,
        prefix="visdom_live",
        hashed_key=uuid.uuid4().hex,
        user_id=owner.id,
        created_at=now - datetime.timedelta(days=age_days),
        last_used_at=(
            None if used_days_ago is None else now - datetime.timedelta(days=used_days_ago)
        ),
    )
    db.add(key)
    return key


def _owner(db):

    user = User(
        id=uuid.uuid4(),
        email=f"owner-{uuid.uuid4().hex[:6]}@example.com",
        username=f"owner-{uuid.uuid4().hex[:6]}",
        password_hash="x",
    )
    db.add(user)
    return user


def test_the_cleanup_page_links_to_the_unused_keys_page(admin_client):
    db = admin_client.staff_db
    _key(db, _owner(db), "forgotten")
    db.commit()

    cleanup = admin_client.get("/admin/janitor").text
    assert 'href="?section=keys"' in cleanup
    assert "Revoke forgotten" not in cleanup

    keys = admin_client.get("/admin/janitor?section=keys").text
    assert "forgotten" in keys
    assert 'name="revoke_one"' in keys


def test_revoking_one_unused_key_switches_it_off_and_records_it(admin_client):
    from app.models import AdminAction

    db = admin_client.staff_db
    owner = _owner(db)
    forgotten = _key(db, owner, "forgotten")
    other = _key(db, owner, "also-forgotten")
    db.commit()

    done = admin_client.post(
        "/admin/janitor",
        data={"intent": "revoke", "key_id": str(forgotten.id)},
        follow_redirects=False,
    )
    assert done.status_code == 303
    assert "Revoked+1+unused+key" in done.headers["location"]

    db.expire_all()
    assert db.get(APIKey, forgotten.id).is_active is False
    assert db.get(APIKey, other.id).is_active is True
    entry = db.query(AdminAction).filter(AdminAction.row_id == str(forgotten.id)).one()
    assert entry.model == "APIKey"
    assert entry.changes["is_active"] is False


def test_revoke_all_switches_off_every_unused_key_and_nothing_else(admin_client):

    db = admin_client.staff_db
    owner = _owner(db)
    stale = [_key(db, owner, f"stale-{n}") for n in range(3)]
    in_use = _key(db, owner, "in-use", used_days_ago=1)
    brand_new = _key(db, owner, "brand-new", age_days=0)
    db.commit()

    admin_client.post("/admin/janitor", data={"intent": "revoke_all"}, follow_redirects=False)

    db.expire_all()
    assert all(db.get(APIKey, key.id).is_active is False for key in stale)
    assert db.get(APIKey, in_use.id).is_active is True
    assert db.get(APIKey, brand_new.id).is_active is True


def test_a_key_that_is_in_use_cannot_be_revoked_from_the_cleanup_page(admin_client):
    """The route is reachable without the page, so the page's list is not
    trusted: a key that is not on it is left alone."""

    db = admin_client.staff_db
    in_use = _key(db, _owner(db), "in-use", used_days_ago=1)
    db.commit()

    done = admin_client.post(
        "/admin/janitor",
        data={"intent": "revoke", "key_id": str(in_use.id)},
        follow_redirects=False,
    )
    assert "Nothing+was+revoked" in done.headers["location"]
    db.expire_all()
    assert db.get(APIKey, in_use.id).is_active is True


def test_a_key_name_cannot_reach_the_pages_javascript(admin_client):
    """Key names are typed by users; they reach the confirmation only as text."""
    db = admin_client.staff_db
    _key(db, _owner(db), '"><script>alert(1)</script>')
    db.commit()

    page = admin_client.get("/admin/janitor?section=keys").text
    assert "Revoke &#34;&gt;&lt;script&gt;alert(1)&lt;/script&gt;?" in page
    assert "<script>alert(1)" not in page


def _workspace(db, slug):
    workspace = Workspace(id=uuid.uuid4(), name=slug, slug=slug)
    db.add(workspace)
    return workspace


def _shared_link(db, workspace, *, expired_days_ago, email=None):
    import datetime

    from app.models import SharedLink

    now = datetime.datetime.now(datetime.timezone.utc)
    link = SharedLink(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        role="member",
        invite_email=email,
        expires_at=now - datetime.timedelta(days=expired_days_ago),
    )
    db.add(link)
    return link


def _invite(db, workspace, email):

    invite = WorkspaceInvite(id=uuid.uuid4(), workspace_id=workspace.id, email=email, role="member")
    db.add(invite)
    return invite


def test_each_leftover_list_links_to_a_page_of_its_own(admin_client):
    db = admin_client.staff_db
    workspace = _workspace(db, "left-behind")
    _shared_link(db, workspace, expired_days_ago=3, email="gone@example.com")
    _invite(db, workspace, _owner(db).email)
    db.commit()

    cleanup = admin_client.get("/admin/janitor").text
    assert 'href="?section=links"' in cleanup
    assert 'href="?section=invites"' in cleanup

    links = admin_client.get("/admin/janitor?section=links").text
    assert "gone@example.com" in links
    assert 'name="delete_one"' in links
    invites = admin_client.get("/admin/janitor?section=invites").text
    assert "left-behind" in invites
    assert 'name="delete_one"' in invites


def test_a_list_with_nothing_on_it_still_links_to_its_page(admin_client):
    """The way in cannot depend on there being something to clean up: staff open
    the page to check, and an empty card with no link reads as a missing feature."""
    cleanup = admin_client.get("/admin/janitor").text
    assert "Nothing to clean up here." in cleanup
    for section in ("keys", "links", "invites"):
        assert f'href="?section={section}"' in cleanup

    empty = admin_client.get("/admin/janitor?section=links")
    assert empty.status_code == 200
    assert "No links to clean up." in empty.text


def test_deleting_one_expired_link_leaves_the_rest_and_records_it(admin_client):
    from app.models import AdminAction, SharedLink

    db = admin_client.staff_db
    workspace = _workspace(db, "two-links")
    doomed = _shared_link(db, workspace, expired_days_ago=3, email="a@example.com")
    kept = _shared_link(db, workspace, expired_days_ago=5, email="b@example.com")
    db.commit()
    doomed_id, kept_id = doomed.id, kept.id

    done = admin_client.post(
        "/admin/janitor?section=links", data={"delete_one": str(doomed_id)}, follow_redirects=False
    )
    assert "Deleted+1+link" in done.headers["location"]
    assert "section=links" in done.headers["location"]

    db.expire_all()
    assert db.get(SharedLink, doomed_id) is None
    assert db.get(SharedLink, kept_id) is not None
    entry = db.query(AdminAction).filter(AdminAction.row_id == str(doomed_id)).one()
    assert (entry.action, entry.model) == ("delete", "SharedLink")
    assert entry.changes["issued_to"] == "a@example.com"


def test_a_link_still_in_date_cannot_be_deleted_from_the_cleanup_page(admin_client):
    from app.models import SharedLink

    db = admin_client.staff_db
    live = _shared_link(db, _workspace(db, "live-link"), expired_days_ago=-3)
    db.commit()

    done = admin_client.post(
        "/admin/janitor?section=links", data={"delete_one": str(live.id)}, follow_redirects=False
    )
    assert "notice_kind=info" in done.headers["location"]
    db.expire_all()
    assert db.get(SharedLink, live.id) is not None


def test_delete_all_removes_only_invites_to_people_who_signed_up(admin_client):

    db = admin_client.staff_db
    workspace = _workspace(db, "invites-here")
    answered = [_invite(db, workspace, _owner(db).email) for _ in range(2)]
    pending = _invite(db, workspace, "not-yet@example.com")
    db.commit()
    answered_ids, pending_id = [invite.id for invite in answered], pending.id

    done = admin_client.post(
        "/admin/janitor?section=invites", data={"intent": "delete_all"}, follow_redirects=False
    )
    assert "Deleted+2+invites" in done.headers["location"]
    db.expire_all()
    assert all(db.get(WorkspaceInvite, invite_id) is None for invite_id in answered_ids)
    assert db.get(WorkspaceInvite, pending_id) is not None


def test_deleting_with_nothing_selected_deletes_nothing(admin_client):

    db = admin_client.staff_db
    invite = _invite(db, _workspace(db, "unselected"), _owner(db).email)
    db.commit()

    done = admin_client.post(
        "/admin/janitor?section=invites", data={"intent": "delete"}, follow_redirects=False
    )
    assert "Select+at+least+one+invite" in done.headers["location"]
    db.expire_all()
    assert db.get(WorkspaceInvite, invite.id) is not None


def test_support_sees_the_leftovers_but_cannot_delete_them(admin_client):
    from app.models import SharedLink

    db = admin_client.staff_db
    link = _shared_link(db, _workspace(db, "support-view"), expired_days_ago=3)
    db.add(
        AdminUser(
            id=uuid.uuid4(),
            email="support@example.com",
            password_hash=get_password_hash("supportpassword"),
            role="support",
            is_active=True,
        )
    )
    db.commit()
    admin_client.post("/admin/login", data={"username": "support@example.com", "password": "supportpassword"})

    page = admin_client.get("/admin/janitor?section=links").text
    assert "but not delete them" in page

    done = admin_client.post(
        "/admin/janitor?section=links", data={"delete_one": str(link.id)}, follow_redirects=False
    )
    assert "notice_kind=error" in done.headers["location"]
    db.expire_all()
    assert db.get(SharedLink, link.id) is not None


def test_moving_a_whole_plan_moves_every_account_on_it(admin_client):
    from app.models import AdminAction

    db = admin_client.staff_db
    movers = [_account(db, email=f"mover{n}@example.com") for n in range(3)]
    staying = _account(db, email="already-paid@example.com")
    staying.tier = "pro"
    db.commit()

    done = admin_client.post(
        "/admin/plan-moves",
        data={"from_plan": "free", "to_plan": "pro"},
        follow_redirects=False,
    )
    assert "Moved+3+accounts" in done.headers["location"]

    db.expire_all()
    assert {db.get(User, user.id).tier for user in movers} == {"pro"}
    assert db.get(User, staying.id).tier == "pro"
    entries = db.query(AdminAction).filter(AdminAction.row_id == str(movers[0].id)).all()
    assert entries and entries[0].changes["moved_from"] == "free"


def test_moving_to_the_same_plan_changes_nothing(admin_client):
    db = admin_client.staff_db
    _account(db, email="staying-put@example.com")

    done = admin_client.post(
        "/admin/plan-moves",
        data={"from_plan": "free", "to_plan": "free"},
        follow_redirects=False,
    )
    assert "notice_kind=info" in done.headers["location"]


def _pick(admin_client, to_plan, accounts, query=""):
    form = {"intent": "move_picked", "to_plan": to_plan, "row_ids": [str(a.id) for a in accounts]}
    return admin_client.post(f"/admin/plan-moves{query}", data=form, follow_redirects=False)


def test_ticked_accounts_move_together_whatever_plan_they_were_on(admin_client):
    from app.models import AdminAction

    db = admin_client.staff_db
    on_free = _account(db, email="picked-free@example.com")
    on_enterprise = _account(db, email="picked-enterprise@example.com")
    on_enterprise.tier = "enterprise"
    already = _account(db, email="picked-already@example.com")
    already.tier = "pro"
    left_alone = _account(db, email="not-picked@example.com")
    db.commit()

    done = _pick(admin_client, "pro", [on_free, on_enterprise, already])
    assert "notice_kind=success" in done.headers["location"]
    assert "Moved+2+accounts+to+pro" in done.headers["location"]
    assert "1+was+already+on+it" in done.headers["location"]

    db.expire_all()
    assert {db.get(User, a.id).tier for a in (on_free, on_enterprise, already)} == {"pro"}
    assert db.get(User, left_alone.id).tier == "free"
    moved_from = {
        entry.row_id: entry.changes["moved_from"]
        for entry in db.query(AdminAction).filter(AdminAction.model == "User")
    }
    assert moved_from == {str(on_free.id): "free", str(on_enterprise.id): "enterprise"}


def test_the_account_list_can_be_searched_and_filtered_by_plan(admin_client):
    db = admin_client.staff_db
    _account(db, email="alpha.search@example.com")
    paid = _account(db, email="beta.search@example.com")
    paid.tier = "pro"
    db.commit()

    everyone = admin_client.get("/admin/plan-moves").text
    assert "alpha.search@example.com" in everyone and "beta.search@example.com" in everyone

    by_name = admin_client.get("/admin/plan-moves?q=ALPHA.search").text
    assert "alpha.search@example.com" in by_name
    assert "beta.search@example.com" not in by_name

    by_plan = admin_client.get("/admin/plan-moves?plan=pro").text
    assert "beta.search@example.com" in by_plan
    assert "alpha.search@example.com" not in by_plan

    nobody = admin_client.get("/admin/plan-moves?q=no-such-account").text
    assert "No account matches that." in nobody


def test_a_search_treats_percent_and_underscore_as_plain_text(admin_client):
    db = admin_client.staff_db
    _account(db, email="plain@example.com")

    assert "plain@example.com" not in admin_client.get("/admin/plan-moves?q=%25").text
    assert "plain@example.com" not in admin_client.get("/admin/plan-moves?q=pl_in").text


def test_moving_with_nothing_ticked_changes_nothing(admin_client):
    from app.models import AdminAction

    db = admin_client.staff_db
    user = _account(db, email="unticked@example.com")

    done = _pick(admin_client, "pro", [])
    assert "notice_kind=info" in done.headers["location"]

    db.expire_all()
    assert db.get(User, user.id).tier == "free"
    assert db.query(AdminAction).count() == 0


def test_ticked_accounts_cannot_go_onto_an_archived_plan(admin_client):
    from app.models import Plan

    db = admin_client.staff_db
    user = _account(db, email="not-onto-retired@example.com")
    db.add(
        Plan(
            id="retired",
            name="Retired",
            price=0,
            sort_order=9,
            is_public=False,
            archived_at=utcnow(),
            limits={"workspaces": 1, "members": 1, "api_keys": 1, "storage_mb": 1, "workspace_storage_mb": 1},
            features=[],
        )
    )
    db.commit()

    done = _pick(admin_client, "retired", [user])
    assert "notice_kind=error" in done.headers["location"]
    db.expire_all()
    assert db.get(User, user.id).tier == "free"


def test_the_search_is_kept_after_a_move(admin_client):
    db = admin_client.staff_db
    user = _account(db, email="kept.filter@example.com")

    done = _pick(admin_client, "pro", [user], query="?q=kept.filter&plan=free")
    assert "q=kept.filter" in done.headers["location"]
    assert "plan=free" in done.headers["location"]


def test_support_cannot_move_ticked_accounts(admin_client):

    db = admin_client.staff_db
    user = _account(db, email="support-cannot-pick@example.com")
    db.add(
        AdminUser(
            id=uuid.uuid4(),
            email="support-picks@example.com",
            password_hash=get_password_hash("supportpassword"),
            role="support",
            is_active=True,
        )
    )
    db.commit()
    admin_client.post(
        "/admin/login",
        data={"username": "support-picks@example.com", "password": "supportpassword"},
    )

    assert _pick(admin_client, "pro", [user]).status_code == 403
    db.expire_all()
    assert db.get(User, user.id).tier == "free"


def test_nobody_can_be_moved_onto_an_archived_plan(admin_client):
    from app.models import Plan

    db = admin_client.staff_db
    user = _account(db, email="not-archived@example.com")
    db.add(
        Plan(
            id="retired",
            name="Retired",
            price=0,
            sort_order=9,
            is_public=False,
            archived_at=utcnow(),
            limits={"workspaces": 1, "members": 1, "api_keys": 1, "storage_mb": 1, "workspace_storage_mb": 1},
            features=[],
        )
    )
    db.commit()

    done = admin_client.post(
        "/admin/plan-moves",
        data={"from_plan": "free", "to_plan": "retired"},
        follow_redirects=False,
    )
    assert "notice_kind=error" in done.headers["location"]
    db.expire_all()
    assert db.get(User, user.id).tier == "free"


def test_support_cannot_reach_the_plan_moves_page(admin_client):

    db = admin_client.staff_db
    user = _account(db, email="support-cannot@example.com")
    db.add(
        AdminUser(
            id=uuid.uuid4(),
            email="support-moves@example.com",
            password_hash=get_password_hash("supportpassword"),
            role="support",
            is_active=True,
        )
    )
    db.commit()
    admin_client.post(
        "/admin/login",
        data={"username": "support-moves@example.com", "password": "supportpassword"},
    )

    assert admin_client.get("/admin/plan-moves").status_code == 403
    refused = admin_client.post(
        "/admin/plan-moves",
        data={"from_plan": "free", "to_plan": "pro"},
        follow_redirects=False,
    )
    assert refused.status_code == 403
    db.expire_all()
    assert db.get(User, user.id).tier == "free"

TEAM_LIMITS = {
    "workspaces": 3,
    "members": 5,
    "api_keys": 4,
    "storage_mb": 2048,
    "workspace_storage_mb": 1024,
}


def _limit_boxes(limits):
    """The plan form's limit inputs, an empty box standing for unlimited."""
    return {f"limits-{key}": "" if value is None else str(value) for key, value in limits.items()}


def _plan_form(plan_id="team", limits=None, **extra):
    form = {
        "id": plan_id,
        "name": "Team",
        "price": "12",
        "sort_order": "5",
        "is_public": "y",
        "features": "3 workspaces",
        "retention_days": "30",
    }
    form.update(_limit_boxes(TEAM_LIMITS if limits is None else limits))
    form.update(extra)
    return form


def test_a_superadmin_can_add_a_plan(admin_client):
    from app.models import Plan

    made = admin_client.post("/admin/plan/create", data=_plan_form(), follow_redirects=False)
    assert made.status_code in (302, 303), made.text

    admin_client.staff_db.expire_all()
    plan = admin_client.staff_db.get(Plan, "team")
    assert plan.limits == TEAM_LIMITS
    assert plan.features == ["3 workspaces"]


def test_features_are_typed_one_to_a_line(admin_client):
    from app.models import Plan

    typed = "5 workspaces\n\n  Priority support  \r\nShared links\n"
    made = admin_client.post(
        "/admin/plan/create", data=_plan_form("lined", features=typed), follow_redirects=False
    )
    assert made.status_code in (302, 303), made.text

    admin_client.staff_db.expire_all()
    assert admin_client.staff_db.get(Plan, "lined").features == [
        "5 workspaces",
        "Priority support",
        "Shared links",
    ]
    page = admin_client.get("/admin/plan/edit/lined").text
    assert "5 workspaces\nPriority support\nShared links" in page.replace("\r\n", "\n")
    assert "[&#34;" not in page and '["5' not in page


def test_an_empty_limit_box_means_unlimited(admin_client):
    from app.models import Plan

    limits = dict(TEAM_LIMITS, members=None, storage_mb=None)
    made = admin_client.post(
        "/admin/plan/create", data=_plan_form("roomy", limits=limits), follow_redirects=False
    )
    assert made.status_code in (302, 303), made.text

    admin_client.staff_db.expire_all()
    assert admin_client.staff_db.get(Plan, "roomy").limits == limits


@pytest.mark.parametrize("typed", ["three", "-1", "1.5", "1e3"])
def test_a_limit_that_is_not_a_whole_number_is_refused(admin_client, typed):
    from app.models import Plan

    form = _plan_form("typo")
    form["limits-workspaces"] = typed
    refused = admin_client.post("/admin/plan/create", data=form, follow_redirects=False)

    assert refused.status_code not in (302, 303)
    assert "Workspaces must be a whole number" in refused.text
    assert 'class="ap-limits is-invalid"' in refused.text
    assert f'value="{typed}"' in refused.text
    admin_client.staff_db.expire_all()
    assert admin_client.staff_db.get(Plan, "typo") is None


def test_the_plan_form_shows_a_box_for_each_limit(admin_client):
    from app import billing

    page = admin_client.get("/admin/plan/edit/free").text

    for key in billing.LIMIT_KEYS:
        assert f'name="limits-{key}"' in page
    assert 'name="limits-workspaces" value="1"' in page
    assert 'name="limits"' not in page

    unlimited = admin_client.get("/admin/plan/edit/enterprise").text
    assert 'name="limits-workspaces" value=""' in unlimited


def test_a_plan_with_a_missing_limit_is_refused(admin_client):
    from app.models import Plan

    refused = admin_client.post(
        "/admin/plan/create",
        data=_plan_form("gappy", limits={"workspaces": 3, "members": 5}),
        follow_redirects=False,
    )
    assert refused.status_code not in (302, 303)
    admin_client.staff_db.expire_all()
    assert admin_client.staff_db.get(Plan, "gappy") is None


def test_a_plan_id_must_be_a_slug(admin_client):
    from app.models import Plan

    refused = admin_client.post(
        "/admin/plan/create", data=_plan_form("Not A Slug!"), follow_redirects=False
    )
    assert refused.status_code not in (302, 303)
    admin_client.staff_db.expire_all()
    assert admin_client.staff_db.query(Plan).filter(Plan.name == "Team").count() == 0


def test_editing_a_plan_changes_its_limits_but_never_its_id(admin_client):
    from app.models import Plan

    admin_client.post(
        "/admin/plan/edit/pro",
        data={
            "id": "renamed",
            "name": "Pro",
            "price": "29",
            "sort_order": "1",
            "is_public": "y",
            "features": "",
            "retention_days": "90",
            **_limit_boxes(
                {
                    "workspaces": 15,
                    "members": None,
                    "api_keys": 20,
                    "storage_mb": 10240,
                    "workspace_storage_mb": 5120,
                }
            ),
        },
        follow_redirects=False,
    )
    admin_client.staff_db.expire_all()
    assert admin_client.staff_db.get(Plan, "renamed") is None
    changed = admin_client.staff_db.get(Plan, "pro").limits
    assert changed["workspaces"] == 15
    assert changed["members"] is None


def test_an_account_already_on_an_archived_plan_can_still_be_suspended(admin_client):
    """Saving for an unrelated reason must not be refused for a plan nobody is
    changing."""
    import datetime

    from app.models import Plan

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
    user = User(
        id=uuid.uuid4(), email="stayer@example.com", username="stayer", password_hash="x", tier="legacy"
    )
    db.add(user)
    db.commit()

    admin_client.post(f"/admin/user/edit/{user.id}", data={"tier": "legacy"}, follow_redirects=False)
    db.expire_all()
    record = db.get(User, user.id)
    assert record.is_active is False
    assert record.tier == "legacy"


def test_the_usage_page_renders_for_staff(admin_client):
    page = admin_client.get("/admin/usage")
    assert page.status_code == 200
    assert "Server" in page.text
    assert "This month, all workspaces" in page.text


def test_the_usage_page_lists_what_each_workspace_used(admin_client):
    import datetime

    from app.models import WorkspaceUsageHour
    from app.routers.usage import month_start

    db = admin_client.staff_db
    owner = User(id=uuid.uuid4(), email="busy@example.com", username="busy", password_hash="x", tier="pro")
    busy = Workspace(id=uuid.uuid4(), name="Busy", slug="busy-one", created_by=owner.id)
    quiet = Workspace(id=uuid.uuid4(), name="Quiet", slug="quiet-one", created_by=owner.id)
    db.add_all([owner, busy, quiet])
    db.commit()
    db.add(
        WorkspaceUsageHour(
            workspace_id=busy.id,
            hour_start=month_start() + datetime.timedelta(days=1, hours=9),
            active_minutes=95,
            writes=1200,
            broadcasts=3400,
            broadcast_bytes=5 * 1024 * 1024,
            peak_bytes=40 * 1024 * 1024,
            current_bytes=40 * 1024 * 1024,
        )
    )
    db.commit()

    page = admin_client.get("/admin/usage").text
    assert "busy-one" in page and "quiet-one" in page
    assert "1h 35m" in page
    assert "1,200" in page
    assert "40.0 MB" in page
    assert page.index("busy-one") < page.index("quiet-one")


def test_support_can_see_usage_and_a_stranger_cannot(admin_client):
    from app.admin.usage_view import UsageView

    class Req:
        def __init__(self, role):
            self.session = {"admin_role": role}

    assert UsageView._allowed(Req("support"))
    assert not UsageView._allowed(Req("stranger"))


def test_the_server_report_survives_a_machine_that_reports_nothing(monkeypatch, db_session):
    """On a development machine there is no /proc; the page must still render."""
    from app.admin import server_stats, usage_view

    monkeypatch.setattr(
        server_stats,
        "snapshot",
        lambda: {"cpus": 2, "load": None, "memory": None, "disk": None, "uptime_seconds": None},
    )
    report = usage_view.server_report(db_session)
    assert report["memory"] is None
    assert report["disk"] is None
    assert report["load_share"] is None


def test_a_full_disk_is_reported_as_a_share():
    from app.admin.usage_view import _share, format_bytes, format_minutes

    assert _share(69, 100) == 69
    assert _share(1, 0) is None
    assert format_bytes(40 * 1024 * 1024) == "40.0 MB"
    assert format_minutes(95) == "1h 35m"


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

KEYS_PAGE = "/admin/janitor?section=keys"


def _sent_to(monkeypatch, fail_for=()):
    from app.admin import panel as admin_panel

    sent = []

    def fake_send(to, subject, body):
        if to in fail_for:
            return False
        sent.append((to, subject, body))
        return True

    monkeypatch.setattr(admin_panel.outbound, "configured", lambda: True)
    monkeypatch.setattr(admin_panel.outbound, "send", fake_send)
    return sent


def test_the_keys_page_says_where_each_key_stands(admin_client):
    db = admin_client.staff_db
    owner = _owner(db)
    _key(db, owner, "never-touched")
    db.commit()

    page = admin_client.get(KEYS_PAGE).text
    assert "never-touched" in page
    assert owner.email in page
    assert "never used" in page


def test_cleanup_stays_selected_on_the_keys_page(admin_client):
    nav = _nav(admin_client.get(KEYS_PAGE).text)
    assert [name for name, (_href, on) in nav.items() if on] == ["Cleanup"]


def test_a_row_button_revokes_only_that_key(admin_client):

    db = admin_client.staff_db
    owner = _owner(db)
    target, other = _key(db, owner, "target"), _key(db, owner, "other")
    db.commit()

    done = admin_client.post(
        KEYS_PAGE,
        data={"revoke_one": str(target.id), "key_ids": [str(target.id), str(other.id)]},
        follow_redirects=False,
    )
    assert "section=keys" in done.headers["location"]
    db.expire_all()
    assert db.get(APIKey, target.id).is_active is False
    assert db.get(APIKey, other.id).is_active is True


def test_revoke_with_nothing_selected_revokes_nothing(admin_client):
    """The bulk button says 'selected'; with none selected it must not fall
    through to revoking everything."""

    db = admin_client.staff_db
    keys = [_key(db, _owner(db), f"keep-{n}") for n in range(2)]
    db.commit()

    done = admin_client.post(KEYS_PAGE, data={"intent": "revoke"}, follow_redirects=False)
    assert "Select+at+least+one+key" in done.headers["location"]
    db.expire_all()
    assert all(db.get(APIKey, key.id).is_active for key in keys)


def test_revoking_the_selected_keys_leaves_the_rest(admin_client):

    db = admin_client.staff_db
    owner = _owner(db)
    a, b, c = (_key(db, owner, name) for name in ("a", "b", "c"))
    db.commit()

    admin_client.post(
        KEYS_PAGE, data={"intent": "revoke", "key_ids": [str(a.id), str(b.id)]}, follow_redirects=False
    )
    db.expire_all()
    assert [db.get(APIKey, k.id).is_active for k in (a, b, c)] == [False, False, True]


def test_notifying_is_refused_while_email_is_not_set_up(admin_client, monkeypatch):
    from app.admin import panel as admin_panel

    monkeypatch.setattr(admin_panel.outbound, "configured", lambda: False)
    db = admin_client.staff_db
    key = _key(db, _owner(db), "quiet")
    db.commit()

    done = admin_client.post(KEYS_PAGE, data={"notify_one": str(key.id)}, follow_redirects=False)
    assert "Email+is+not+set+up" in done.headers["location"]
    db.expire_all()
    assert db.get(APIKey, key.id).owner_notified_at is None


def test_each_owner_gets_one_email_listing_all_their_keys(admin_client, monkeypatch):
    import datetime


    sent = _sent_to(monkeypatch)
    db = admin_client.staff_db
    owner = _owner(db)
    first, second = _key(db, owner, "first-key"), _key(db, owner, "second-key")
    db.commit()

    admin_client.post(
        KEYS_PAGE,
        data={"intent": "notify", "key_ids": [str(first.id), str(second.id)]},
        follow_redirects=False,
    )
    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == owner.email
    assert "first-key" in body and "second-key" in body

    db.expire_all()
    marked = db.get(APIKey, first.id)
    deadline = marked.revoke_after.replace(tzinfo=marked.revoke_after.tzinfo or datetime.timezone.utc)
    days = (deadline - datetime.datetime.now(datetime.timezone.utc)).days
    assert marked.owner_notified_at is not None
    assert 29 <= days <= 30


def test_a_key_is_only_marked_once_its_owners_email_went_out(admin_client, monkeypatch):
    """Otherwise a failed send could end with a key revoked without warning."""

    db = admin_client.staff_db
    reachable, unreachable = _owner(db), _owner(db)
    good, bad = _key(db, reachable, "good"), _key(db, unreachable, "bad")
    db.commit()
    _sent_to(monkeypatch, fail_for=(unreachable.email,))

    done = admin_client.post(
        KEYS_PAGE, data={"intent": "notify", "key_ids": [str(good.id), str(bad.id)]}, follow_redirects=False
    )
    assert "Could+not+email" in done.headers["location"]
    db.expire_all()
    assert db.get(APIKey, good.id).owner_notified_at is not None
    assert db.get(APIKey, bad.id).owner_notified_at is None


def test_only_keys_past_their_notice_are_revoked_as_due(admin_client):
    import datetime


    now = datetime.datetime.now(datetime.timezone.utc)
    db = admin_client.staff_db
    owner = _owner(db)
    overdue, waiting = _key(db, owner, "overdue"), _key(db, owner, "waiting")
    day = datetime.timedelta(days=1)
    overdue.owner_notified_at, overdue.revoke_after = now - 31 * day, now - day
    waiting.owner_notified_at, waiting.revoke_after = now - 5 * day, now + 25 * day
    db.commit()

    assert "due for revocation" in admin_client.get(KEYS_PAGE).text
    admin_client.post(KEYS_PAGE, data={"intent": "revoke_due"}, follow_redirects=False)
    db.expire_all()
    assert db.get(APIKey, overdue.id).is_active is False
    assert db.get(APIKey, waiting.id).is_active is True


def test_keys_past_their_notice_are_switched_off_without_anyone_pressing_a_button(admin_client):
    import datetime

    from app.admin import janitor
    from app.models import AdminAction

    now = datetime.datetime.now(datetime.timezone.utc)
    day = datetime.timedelta(days=1)
    db = admin_client.staff_db
    owner = _owner(db)
    overdue = _key(db, owner, "overdue")
    waiting = _key(db, owner, "waiting")
    used_since = _key(db, owner, "used-since", used_days_ago=2)
    never_told = _key(db, owner, "never-told")
    overdue.owner_notified_at, overdue.revoke_after = now - 31 * day, now - day
    waiting.owner_notified_at, waiting.revoke_after = now - 5 * day, now + 25 * day
    used_since.owner_notified_at, used_since.revoke_after = now - 31 * day, now - day
    db.commit()

    revoked = janitor.revoke_due_keys(db)

    assert [name for _id, name in revoked] == ["overdue"]
    db.expire_all()
    assert db.get(APIKey, overdue.id).is_active is False
    assert db.get(APIKey, waiting.id).is_active is True
    assert db.get(APIKey, used_since.id).is_active is True
    assert db.get(APIKey, never_told.id).is_active is True

    trail = db.query(AdminAction).filter(AdminAction.row_id == str(overdue.id)).one()
    assert trail.admin_email == janitor.AUTOMATIC
    assert trail.changes == {"is_active": False, "revoked_from": "notice period ended"}


def test_with_nothing_due_the_automatic_revoke_does_nothing(admin_client):
    from app.admin import janitor
    from app.models import AdminAction

    db = admin_client.staff_db
    _key(db, _owner(db), "fine")
    db.commit()

    assert janitor.revoke_due_keys(db) == []
    assert db.query(AdminAction).filter(AdminAction.model == "APIKey").count() == 0


def test_using_a_key_after_its_notice_cancels_the_notice():
    import datetime
    import types

    from app.admin import janitor

    now = datetime.datetime.now(datetime.timezone.utc)
    key = types.SimpleNamespace(
        owner_notified_at=now - datetime.timedelta(days=10),
        last_used_at=now - datetime.timedelta(days=2),
        revoke_after=now - datetime.timedelta(days=1),
    )
    assert janitor.notice_is_current(key) is False
    assert janitor.is_due(key, now) is False


def _trash_post(admin_client, intent, accounts, query=""):
    form = {"intent": intent, "row_ids": [str(a.id) for a in accounts]}
    return admin_client.post(f"/admin/account-trash{query}", data=form, follow_redirects=False)


def test_trashing_locks_an_account_out_and_deletes_nothing(admin_client):
    from app.models import AdminAction, Workspace

    db = admin_client.staff_db
    user = _account(db, email="to-the-trash@example.com")
    workspace = _workspace(db, "trashed-owner-lab")
    workspace.created_by = user.id
    before = user.token_version or 0
    db.commit()

    done = _trash_post(admin_client, "trash", [user])
    assert "notice_kind=success" in done.headers["location"]

    db.expire_all()
    trashed = db.get(User, user.id)
    assert trashed.trashed_at is not None
    assert trashed.trashed_by == "staff@example.com"
    assert trashed.is_active is False
    assert trashed.token_version == before + 1
    assert db.get(Workspace, workspace.id) is not None
    entry = db.query(AdminAction).filter(AdminAction.row_id == str(user.id)).one()
    assert entry.changes == {"trashed": True, "email": "to-the-trash@example.com"}

    page = admin_client.get("/admin/account-trash").text
    assert page.count("to-the-trash@example.com") >= 1
    assert "1 in the trash" in page


def test_restoring_puts_an_account_back(admin_client):

    db = admin_client.staff_db
    user = _account(db, email="back-again@example.com")
    _trash_post(admin_client, "trash", [user])

    done = _trash_post(admin_client, "restore", [user])
    assert "notice_kind=success" in done.headers["location"]

    db.expire_all()
    back = db.get(User, user.id)
    assert back.trashed_at is None and back.trashed_by is None
    assert back.is_active is True
    assert "The trash is empty." in admin_client.get("/admin/account-trash").text


def test_an_account_can_only_be_deleted_from_the_trash(admin_client):

    db = admin_client.staff_db
    user = _account(db, email="not-trashed-yet@example.com")

    done = _trash_post(admin_client, "delete", [user])
    assert "notice_kind=error" in done.headers["location"]
    db.expire_all()
    assert db.get(User, user.id) is not None


def test_deleting_from_the_trash_removes_the_account_and_is_recorded(admin_client, monkeypatch):
    from app import account_deletion
    from app.models import AdminAction

    monkeypatch.setattr(account_deletion, "drop_workspace", lambda workspace_id: {"bytes": 0})
    db = admin_client.staff_db
    user = _account(db, email="gone-for-good@example.com")
    user_id = user.id
    _trash_post(admin_client, "trash", [user])

    done = _trash_post(admin_client, "delete", [user])
    assert "Deleted+1+account+for+good" in done.headers["location"]

    db.expire_all()
    assert db.get(User, user_id) is None
    entry = (
        db.query(AdminAction)
        .filter(AdminAction.row_id == str(user_id), AdminAction.action == "delete")
        .one()
    )
    assert entry.admin_email == "staff@example.com"
    assert entry.changes["email"] == "gone-for-good@example.com"
    assert entry.changes["reason"] == "deleted from the trash by staff"


def test_an_account_that_owns_a_shared_workspace_is_kept(admin_client):

    db = admin_client.staff_db
    owner = _account(db, email="owner-of-shared@example.com")
    member = _account(db, email="member-of-shared@example.com")
    workspace = _workspace(db, "shared-lab")
    workspace.created_by = owner.id
    db.add(Membership(user_id=owner.id, workspace_id=workspace.id, role="admin", status="active"))
    db.add(Membership(user_id=member.id, workspace_id=workspace.id, role="member", status="active"))
    db.commit()
    _trash_post(admin_client, "trash", [owner])

    page = admin_client.get("/admin/account-trash").text
    assert "Cannot be deleted yet: it owns shared-lab" in page

    done = _trash_post(admin_client, "delete", [owner])
    assert "notice_kind=error" in done.headers["location"]
    assert "still+owns+shared-lab" in done.headers["location"]
    db.expire_all()
    assert db.get(User, owner.id) is not None


def test_a_trashed_account_cannot_be_switched_back_on_from_its_form(admin_client):

    db = admin_client.staff_db
    user = _account(db, email="form-cannot-revive@example.com")
    _trash_post(admin_client, "trash", [user])

    refused = admin_client.post(
        f"/admin/user/edit/{user.id}", data=_user_form(user), follow_redirects=False
    )
    assert refused.status_code not in (302, 303)
    db.expire_all()
    assert db.get(User, user.id).is_active is False


def test_the_trash_list_can_be_searched(admin_client):
    db = admin_client.staff_db
    _account(db, email="needle.trash@example.com")
    _account(db, email="haystack.trash@example.com")

    found = admin_client.get("/admin/account-trash?q=NEEDLE").text
    assert "needle.trash@example.com" in found
    assert "haystack.trash@example.com" not in found


@pytest.mark.parametrize("role", ["admin", "support"])
def test_only_a_superadmin_reaches_the_account_trash(admin_client, role):

    db = admin_client.staff_db
    user = _account(db, email="not-theirs-to-trash@example.com")
    db.add(
        AdminUser(
            id=uuid.uuid4(),
            email=f"{role}-trash@example.com",
            password_hash=get_password_hash("their-staff-password"),
            role=role,
            is_active=True,
        )
    )
    db.commit()
    admin_client.post(
        "/admin/login", data={"username": f"{role}-trash@example.com", "password": "their-staff-password"}
    )

    assert admin_client.get("/admin/account-trash").status_code == 403
    assert _trash_post(admin_client, "trash", [user]).status_code == 403
    assert "Account trash" not in admin_client.get("/admin/").text
    db.expire_all()
    assert db.get(User, user.id).trashed_at is None


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


def test_trashing_and_deleting_are_granted_apart(admin_client):

    db = admin_client.staff_db
    member = _staff(db, "trasher-admin@example.com", "admin")
    user = _account(db, email="half-granted@example.com")
    _grant(admin_client, single=[("trash_accounts", member)])
    _sign_in(admin_client, "trasher-admin@example.com")

    assert "notice_kind=success" in _trash_post(admin_client, "trash", [user]).headers["location"]
    refused = _trash_post(admin_client, "delete", [user])
    assert "notice_kind=error" in refused.headers["location"]
    db.expire_all()
    assert db.get(User, user.id) is not None

