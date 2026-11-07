# Copyright 2017-present, The Visdom Authors
"""Invites nobody answers stop holding a seat after INVITE_EXPIRY_DAYS."""
import datetime
import uuid

import pytest

from app import invites
from app.models import Membership, WorkspaceInvite, utcnow


@pytest.fixture
def expiry(monkeypatch):
    monkeypatch.setattr(invites.settings, "INVITE_EXPIRY_DAYS", 30)


def _invite(client, admin, workspace, email):
    """Send a member invite as this admin and require the workspace to accept it."""
    sent = client.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": email, "role": "member"},
        headers=admin["headers"],
    )
    assert sent.status_code == 201, sent.text


def _later(days):
    return utcnow() + datetime.timedelta(days=days)


def test_an_unanswered_email_invite_expires(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, "nobody-yet@example.com")

    assert invites.expire(db_session, now=_later(29)) == 0
    assert db_session.query(WorkspaceInvite).count() == 1
    assert invites.expire(db_session, now=_later(31)) == 1
    assert db_session.query(WorkspaceInvite).count() == 0


def test_an_unanswered_member_invite_expires(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    invitee = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, invitee["email"])

    def pending():
        return db_session.query(Membership).filter(Membership.status == "pending_acceptance").count()

    assert pending() == 1
    invites.expire(db_session, now=_later(29))
    assert pending() == 1
    invites.expire(db_session, now=_later(31))
    assert pending() == 0


def test_an_accepted_invite_is_never_removed(client, db_session, make_user, make_workspace, add_member, expiry):
    owner = make_user()
    member = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)

    assert invites.expire(db_session, now=_later(365)) == 0


def test_an_invite_keeps_its_age_when_the_invitee_registers(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, "late@example.com")
    sent = db_session.query(WorkspaceInvite).one().created_at

    make_user(email="late@example.com")
    membership = db_session.query(Membership).filter(Membership.status == "pending_acceptance").one()
    assert membership.invited_at == sent


def test_zero_days_turns_expiry_off(client, db_session, make_user, make_workspace, monkeypatch):
    monkeypatch.setattr(invites.settings, "INVITE_EXPIRY_DAYS", 0)
    owner = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, "forever@example.com")

    assert invites.expire(db_session, now=_later(365)) == 0


def _age(db_session, days):
    """Backdate every invite by ``days``, as if the sweep had not run yet."""
    for invite in db_session.query(WorkspaceInvite).all():
        invite.created_at = utcnow() - datetime.timedelta(days=days)
    for membership in db_session.query(Membership).filter(Membership.status == "pending_acceptance"):
        membership.invited_at = utcnow() - datetime.timedelta(days=days)
    db_session.commit()


def test_an_expired_invite_cannot_be_accepted_before_the_sweep(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    invitee = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, invitee["email"])
    _age(db_session, 31)

    accepted = client.post(f"/api/v1/workspaces/{workspace['id']}/members/me/accept", headers=invitee["headers"])
    assert accepted.status_code == 410, accepted.text
    db_session.expire_all()
    assert db_session.query(Membership).filter(Membership.user_id == uuid.UUID(invitee["id"])).count() == 0


def test_a_fresh_invite_can_still_be_accepted(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    invitee = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, invitee["email"])
    _age(db_session, 29)

    accepted = client.post(f"/api/v1/workspaces/{workspace['id']}/members/me/accept", headers=invitee["headers"])
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "active"


def test_registering_does_not_revive_an_expired_email_invite(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, "stale@example.com")
    _age(db_session, 31)

    make_user(email="stale@example.com")
    db_session.expire_all()
    assert db_session.query(Membership).filter(Membership.status == "pending_acceptance").count() == 0
    assert db_session.query(WorkspaceInvite).count() == 0


def test_invite_cleanup_runs_with_account_deletion_off(monkeypatch):
    import asyncio

    from app import main

    started = []

    async def fake_expire(hours):
        started.append(hours)

    async def fake_delete(hours):
        raise AssertionError("account deletion should be off")

    monkeypatch.setattr(main.settings, "ACCOUNT_DELETION_HOURS", 0)
    monkeypatch.setattr(main.settings, "RETENTION_SWEEP_HOURS", 0)
    monkeypatch.setattr(main.settings, "INVITE_EXPIRY_DAYS", 30)
    monkeypatch.setattr(main, "_expire_invites_forever", fake_expire)
    monkeypatch.setattr(main, "_delete_accounts_forever", fake_delete)

    async def run():
        async with main.lifespan(main.app):
            await asyncio.sleep(0)

    asyncio.run(run())
    assert started == [main.INVITE_SWEEP_HOURS]


def test_the_invite_expiry_loop_runs_expire_once_on_each_tick(monkeypatch):
    import asyncio

    from app import main

    waits = []
    runs = []

    async def fake_sleep(seconds):
        """Record the delay, and cancel the loop on the third wait.

        The first wait is the startup delay and the next two are ticks. Stopping
        there leaves three passes to observe, including the one that fails.
        """
        if len(waits) == 3:
            raise asyncio.CancelledError
        waits.append(seconds)

    def fake_expire_once():
        """Record the pass, and fail the second one.

        The loop has to log that failure and keep going, so the third pass
        still runs.
        """
        runs.append(len(waits))
        if len(runs) == 2:
            raise RuntimeError("database went away")
        return 1

    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main.invites, "expire_once", fake_expire_once)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main._expire_invites_forever(6))

    # First wait is the startup delay, then one wait per tick. A failing tick
    # is logged and the loop carries on to the next one.
    assert waits == [main.FIRST_TICK_SECONDS, 6 * 3600, 6 * 3600]
    assert runs == [1, 2, 3]


def test_an_expired_member_invite_can_be_sent_again(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    invitee = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, invitee["email"])
    _age(db_session, 31)

    _invite(client, owner, workspace, invitee["email"])
    db_session.expire_all()
    membership = db_session.query(Membership).filter(Membership.user_id == uuid.UUID(invitee["id"])).one()
    assert membership.status == "pending_acceptance"
    assert not invites.is_expired(membership.invited_at)


def test_an_expired_email_invite_can_be_sent_again(client, db_session, make_user, make_workspace, expiry):
    owner = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, "again@example.com")
    _age(db_session, 31)

    _invite(client, owner, workspace, "again@example.com")
    db_session.expire_all()
    invite = db_session.query(WorkspaceInvite).one()
    assert not invites.is_expired(invite.created_at)


def test_a_live_invite_or_member_still_blocks_a_second_invite(
    client, db_session, make_user, make_workspace, add_member, expiry
):
    owner = make_user()
    invitee = make_user()
    member = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)
    _invite(client, owner, workspace, invitee["email"])
    _age(db_session, 31)
    for membership in db_session.query(Membership).filter(Membership.user_id == uuid.UUID(member["id"])):
        membership.invited_at = utcnow() - datetime.timedelta(days=31)
    db_session.commit()

    again = client.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": member["email"], "role": "member"},
        headers=owner["headers"],
    )
    assert again.status_code == 400, again.text

    _invite(client, owner, workspace, invitee["email"])
    twice = client.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": invitee["email"], "role": "member"},
        headers=owner["headers"],
    )
    assert twice.status_code == 400, twice.text


def test_expiry_sweeps_have_supporting_indexes():
    """The sweep filters are ``created_at`` and ``status, invited_at``."""
    invite_indexes = {
        index.name: [column.name for column in index.columns]
        for index in WorkspaceInvite.__table__.indexes
    }
    membership_indexes = {
        index.name: [column.name for column in index.columns]
        for index in Membership.__table__.indexes
    }
    assert invite_indexes["ix_workspace_invites_created_at"] == ["created_at"]
    assert membership_indexes["ix_memberships_status_invited_at"] == ["status", "invited_at"]


def test_invite_expiry_migrations_stay_one_line():
    """This branch has one Alembic head, the index revision after invite expiry.

    The retention branch adds a different child of ``a3e8d5c7b214``. That
    sibling is not in this tree; merging both later needs a merge revision.
    """
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert heads == ["e1b6c4d82a57"]
    assert script.get_revision(heads[0]).down_revision == "c4d8a1e6f925"


def test_the_index_migration_creates_and_drops_the_sweep_indexes(tmp_path):
    import importlib.util
    from pathlib import Path

    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine, inspect

    from app.database import Base

    path = Path(__file__).resolve().parents[1] / "alembic/versions/e1b6c4d82a57_invite_expiry_indexes.py"
    spec = importlib.util.spec_from_file_location("invite_expiry_indexes", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path}/indexes.db")
    Base.metadata.create_all(engine)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP INDEX IF EXISTS ix_workspace_invites_created_at")
            connection.exec_driver_sql("DROP INDEX IF EXISTS ix_memberships_status_invited_at")
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
            invite_names = {index["name"] for index in inspect(connection).get_indexes("workspace_invites")}
            membership_columns = {
                tuple(index["column_names"]) for index in inspect(connection).get_indexes("memberships")
            }
            assert "ix_workspace_invites_created_at" in invite_names
            assert ("status", "invited_at") in membership_columns
            with Operations.context(context):
                migration.downgrade()
            invite_names = {index["name"] for index in inspect(connection).get_indexes("workspace_invites")}
            membership_columns = {
                tuple(index["column_names"]) for index in inspect(connection).get_indexes("memberships")
            }
            assert "ix_workspace_invites_created_at" not in invite_names
            assert ("status", "invited_at") not in membership_columns
    finally:
        engine.dispose()


def _separate_database(tmp_path):
    """A client whose commits are visible to a second connection.

    The shared test session rolls every request back together, so it cannot
    show a sweep transaction that has already committed.
    """
    from contextlib import contextmanager

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    from app.billing import seed_default_plans
    from app.database import Base
    from app.dependencies import get_db
    from app.main import app

    @contextmanager
    def opened():
        engine = create_engine(
            f"sqlite:///{tmp_path}/separate.db",
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        seeder = SessionLocal()
        try:
            seed_default_plans(seeder)
        finally:
            seeder.close()

        def override_get_db():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                yield client, SessionLocal
        finally:
            app.dependency_overrides.pop(get_db, None)
            engine.dispose()

    return opened()


def test_accepting_while_the_sweep_deletes_the_row_is_expired_not_a_server_error(tmp_path, monkeypatch):
    """A committed sweep delete after the row was loaded must not become a 500.

    The acceptance request holds the membership, then the sweep's transaction
    removes it. The following UPDATE matches nothing. The answer is the same
    410 an already-expired invite gets.
    """
    import app.routers.workspaces as workspaces

    with _separate_database(tmp_path) as (client, SessionLocal):
        owner = _registered(client)
        invitee = _registered(client)
        _promote(SessionLocal, owner["email"])
        created = client.post(
            "/api/v1/workspaces",
            json={"name": "Race", "slug": "race-workspace"},
            headers=owner["headers"],
        )
        assert created.status_code == 201, created.text
        workspace = created.json()
        _invite(client, owner, workspace, invitee["email"])

        real_refuse = workspaces.refuse_if_full

        def delete_pending_then_continue(db, owner_user):
            """Remove the pending row the way the sweep does, then carry on."""
            real_refuse(db, owner_user)
            other = SessionLocal()
            try:
                removed = (
                    other.query(Membership)
                    .filter(Membership.status == "pending_acceptance")
                    .delete(synchronize_session=False)
                )
                assert removed == 1
                other.commit()
            finally:
                other.close()

        monkeypatch.setattr(workspaces, "refuse_if_full", delete_pending_then_continue)
        accepted = client.post(
            f"/api/v1/workspaces/{workspace['id']}/members/me/accept",
            headers=invitee["headers"],
        )
        assert accepted.status_code == 410, accepted.text
        assert accepted.json()["detail"] == "This invite has expired."
        checker = SessionLocal()
        try:
            left = checker.query(Membership).filter(Membership.user_id == uuid.UUID(invitee["id"])).count()
        finally:
            checker.close()
        assert left == 0


def _registered(client):
    """Create a signed-in user on whatever database this client is using."""
    email = f"race-{uuid.uuid4().hex[:8]}@example.com"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "securepassword"},
    )
    assert registered.status_code == 201, registered.text
    logged_in = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "securepassword"},
    )
    assert logged_in.status_code == 200, logged_in.text
    return {
        "id": registered.json()["id"],
        "email": email,
        "headers": {"Authorization": f"Bearer {logged_in.json()['access_token']}"},
    }


def _promote(session_maker, email):
    """Lift the workspace limit so this test is about the invite race."""
    from app.models import User

    db = session_maker()
    try:
        record = db.query(User).filter(User.email == email).one()
        record.tier = "enterprise"
        db.commit()
    finally:
        db.close()


def test_a_stale_write_that_leaves_the_invite_is_not_reported_as_expired(tmp_path, monkeypatch):
    """``StaleDataError`` is the expired outcome only when the row is gone.

    Uses a database whose commits stick, so rolling the failed acceptance back
    does not also undo the invite the way the shared test transaction would.
    """
    from sqlalchemy.orm import Session
    from sqlalchemy.orm.exc import StaleDataError

    with _separate_database(tmp_path) as (client, SessionLocal):
        owner = _registered(client)
        invitee = _registered(client)
        _promote(SessionLocal, owner["email"])
        created = client.post(
            "/api/v1/workspaces",
            json={"name": "Stale", "slug": "stale-workspace"},
            headers=owner["headers"],
        )
        assert created.status_code == 201, created.text
        workspace = created.json()
        _invite(client, owner, workspace, invitee["email"])

        def boom(self):
            raise StaleDataError("simulated stale write")

        monkeypatch.setattr(Session, "commit", boom)
        with pytest.raises(StaleDataError):
            client.post(
                f"/api/v1/workspaces/{workspace['id']}/members/me/accept",
                headers=invitee["headers"],
            )
        checker = SessionLocal()
        try:
            membership = checker.query(Membership).filter(Membership.user_id == uuid.UUID(invitee["id"])).one()
            assert membership.status == "pending_acceptance"
        finally:
            checker.close()


def test_an_unrelated_database_error_while_accepting_is_not_reported_as_expired(
    client, db_session, make_user, make_workspace, expiry, monkeypatch
):
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    owner = make_user()
    invitee = make_user()
    workspace = make_workspace(owner)
    _invite(client, owner, workspace, invitee["email"])

    def boom(self):
        raise OperationalError("UPDATE memberships", {}, Exception("disk full"))

    monkeypatch.setattr(Session, "commit", boom)
    with pytest.raises(OperationalError):
        client.post(
            f"/api/v1/workspaces/{workspace['id']}/members/me/accept",
            headers=invitee["headers"],
        )

