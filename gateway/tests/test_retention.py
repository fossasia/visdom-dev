# Copyright 2017-present, The Visdom Authors
"""Removing the work a plan no longer keeps.

The window comes from the plan of whoever owns the workspace, and the sweep has
to reach the instance that holds it, because the instances share a disk and a
file deleted from the wrong one comes back. Deleting is off unless asked for,
which is the behaviour most worth pinning down: this is the one job whose
purpose is destroying work.
"""
import datetime
import uuid

import pytest

from app import retention
from app.models import Plan, User, Workspace, utcnow


@pytest.fixture
def instances(monkeypatch):
    monkeypatch.setattr(retention, "instance_addresses", lambda: ["visdom-1:8097", "visdom-2:8097"])


class Recorder:
    """Stands in for the instances, remembering what each was asked."""

    def __init__(self, loaded_at=None, envs=("january",)):
        self.loaded_at = loaded_at
        self.envs = list(envs)
        self.calls = []

    def __call__(self, address, workspace_id, days, dry_run, timeout):
        self.calls.append({"address": address, "days": days, "dry_run": dry_run})
        return {
            "workspace_id": str(workspace_id),
            "loaded": address == self.loaded_at,
            "envs": self.envs,
            "removed": 0 if dry_run else len(self.envs),
        }


def _owner(db_session, tier):
    user = User(
        id=uuid.uuid4(),
        email=f"owner-{uuid.uuid4().hex[:6]}@example.com",
        username=f"owner-{uuid.uuid4().hex[:6]}",
        password_hash="x",
        tier=tier,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _workspace(db_session, owner, slug="kept", **extra):
    workspace = Workspace(id=uuid.uuid4(), name=slug, slug=slug, created_by=owner.id, **extra)
    db_session.add(workspace)
    db_session.commit()
    return workspace


def test_the_window_comes_from_the_owners_plan(db_session):
    free = _workspace(db_session, _owner(db_session, "free"), slug="free-one")
    paid = _workspace(db_session, _owner(db_session, "pro"), slug="pro-one")

    assert retention.window_for(db_session, free) == 7
    assert retention.window_for(db_session, paid) == 90


def test_a_plan_that_keeps_everything_is_never_swept(db_session, instances):
    plan = db_session.query(Plan).filter(Plan.id == "enterprise").one()
    assert plan.retention_days is None
    _workspace(db_session, _owner(db_session, "enterprise"), slug="forever")

    asked = Recorder()
    summary = retention.sweep(db_session, enforce=True, ask=asked)

    assert summary["visited"] == 0
    assert asked.calls == []


def test_reporting_asks_every_instance_and_removes_nothing(db_session, instances):
    _workspace(db_session, _owner(db_session, "free"), slug="reported")

    asked = Recorder(loaded_at="visdom-2:8097")
    summary = retention.sweep(db_session, enforce=False, ask=asked)

    assert summary["with_expired"] == 1
    assert summary["removed"] == 0
    assert [call["dry_run"] for call in asked.calls] == [True, True]
    assert summary["workspaces"][0]["expired"] == ["january"]


def test_the_removal_is_sent_to_the_instance_holding_the_workspace(db_session, instances):
    """The instances share a disk. Sweeping from one that does not hold the
    workspace deletes files the holder writes back from memory."""
    _workspace(db_session, _owner(db_session, "free"), slug="held")

    asked = Recorder(loaded_at="visdom-2:8097")
    summary = retention.sweep(db_session, enforce=True, ask=asked)

    removals = [call for call in asked.calls if not call["dry_run"]]
    assert len(removals) == 1
    assert removals[0]["address"] == "visdom-2:8097"
    assert summary["removed"] == 1


def test_a_workspace_no_instance_holds_is_swept_anyway(db_session, instances):
    """A dormant workspace is nobody's, and its files still age."""
    _workspace(db_session, _owner(db_session, "free"), slug="dormant")

    asked = Recorder(loaded_at=None)
    retention.sweep(db_session, enforce=True, ask=asked)

    removals = [call for call in asked.calls if not call["dry_run"]]
    assert len(removals) == 1


def test_suspended_and_trashed_workspaces_are_left_alone(db_session, instances):
    import datetime

    owner = _owner(db_session, "free")
    _workspace(db_session, owner, slug="stopped", is_active=False)
    _workspace(
        db_session,
        owner,
        slug="binned",
        trashed_at=datetime.datetime.now(datetime.timezone.utc),
    )

    asked = Recorder()
    summary = retention.sweep(db_session, enforce=True, ask=asked)

    assert summary["visited"] == 0
    assert asked.calls == []


def test_an_instance_that_does_not_answer_does_not_stop_the_sweep(db_session, instances):
    _workspace(db_session, _owner(db_session, "free"), slug="patchy")

    def flaky(address, workspace_id, days, dry_run, timeout):
        if address == "visdom-1:8097":
            return None
        return {"loaded": True, "envs": ["january"], "removed": 0 if dry_run else 1}

    summary = retention.sweep(db_session, enforce=True, ask=flaky)

    assert summary["removed"] == 1


def test_a_dormant_looking_workspace_waits_when_an_instance_is_silent(db_session, instances):
    """The silent one may be the holder, and sweeping beside it loses nothing
    for good: its next save writes the files straight back."""
    _workspace(db_session, _owner(db_session, "free"), slug="unsure")
    asked = []

    def flaky(address, workspace_id, days, dry_run, timeout):
        asked.append((address, dry_run))
        if address == "visdom-1:8097":
            return None
        return {"loaded": False, "envs": ["january"], "removed": 0 if dry_run else 1}

    summary = retention.sweep(db_session, enforce=True, ask=flaky)

    assert summary["removed"] == 0
    assert all(dry_run for _address, dry_run in asked)


@pytest.fixture
def rules(monkeypatch):
    def _set(enforce=False, starts=None, warn=3):
        monkeypatch.setattr(retention.settings, "RETENTION_ENFORCE", enforce)
        monkeypatch.setattr(retention.settings, "RETENTION_STARTS", starts)
        monkeypatch.setattr(retention.settings, "RETENTION_WARN_DAYS", warn)
    return _set


TODAY = datetime.date(2026, 10, 1)


def test_a_plan_that_keeps_everything_says_so(db_session, instances, rules):
    rules(enforce=True)
    ask = Recorder()
    notice = retention.notice(db_session, _workspace(db_session, _owner(db_session, "enterprise")), ask=ask)
    assert notice["state"] == "forever"
    assert notice["days"] is None
    assert notice["expiring"] is None
    assert ask.calls == []


def test_before_deleting_is_switched_on_only_the_window_is_shown(db_session, instances, rules):
    rules(enforce=False)
    ask = Recorder()
    notice = retention.notice(db_session, _workspace(db_session, _owner(db_session, "free")), ask=ask)
    assert notice["state"] == "not_enforced"
    assert notice["days"] == 7
    assert notice["plan"] == "Free"
    assert notice["expiring"] is None
    assert ask.calls == []


def test_a_start_date_names_what_would_go_on_that_day(db_session, instances, rules):
    rules(enforce=True, starts=TODAY + datetime.timedelta(days=5))
    ask = Recorder(envs=["old-run"])
    workspace = _workspace(db_session, _owner(db_session, "free"))
    notice = retention.notice(db_session, workspace, ask=ask, today=TODAY)
    assert notice["state"] == "scheduled"
    assert notice["starts_on"] == TODAY + datetime.timedelta(days=5)
    assert notice["expiring"] == ["old-run"]
    assert {call["days"] for call in ask.calls} == {2}
    assert all(call["dry_run"] for call in ask.calls)


def test_once_deleting_what_goes_in_the_next_few_days_is_listed(db_session, instances, rules):
    rules(enforce=True, warn=3)
    ask = Recorder(envs=["b", "a"])
    workspace = _workspace(db_session, _owner(db_session, "free"))
    notice = retention.notice(db_session, workspace, ask=ask, today=TODAY)
    assert notice["state"] == "active"
    assert notice["expiring"] == ["a", "b"]
    assert {call["days"] for call in ask.calls} == {4}
    assert all(call["dry_run"] for call in ask.calls)


def test_a_look_ahead_past_the_window_still_asks_for_a_positive_age(db_session, instances, rules):
    rules(enforce=True, starts=TODAY + datetime.timedelta(days=30))
    ask = Recorder()
    retention.notice(db_session, _workspace(db_session, _owner(db_session, "free")), ask=ask, today=TODAY)
    assert all(call["days"] > 0 for call in ask.calls)


def test_no_answer_is_not_the_same_as_nothing_going(db_session, instances, rules):
    rules(enforce=True)
    notice = retention.notice(
        db_session,
        _workspace(db_session, _owner(db_session, "free")),
        ask=lambda *args: None,
        today=TODAY,
    )
    assert notice["state"] == "active"
    assert notice["expiring"] is None


def test_a_start_date_holds_the_sweep_back_until_it_arrives(rules):
    rules(enforce=True, starts=TODAY)
    assert retention.enforcing(TODAY - datetime.timedelta(days=1)) is False
    assert retention.enforcing(TODAY) is True
    rules(enforce=False, starts=TODAY)
    assert retention.enforcing(TODAY) is False


def test_members_can_read_the_notice_and_others_cannot(client, make_user, make_workspace, add_member):
    owner = make_user()
    member = make_user()
    outsider = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)

    seen = client.get(f"/api/v1/workspaces/{workspace['id']}/retention", headers=member["headers"])
    assert seen.status_code == 200
    assert seen.json()["state"] == "forever"
    hidden = client.get(f"/api/v1/workspaces/{workspace['id']}/retention", headers=outsider["headers"])
    assert hidden.status_code == 404


def test_no_transaction_is_open_while_an_instance_is_asked(db_session, instances):
    _workspace(db_session, _owner(db_session, "free"), slug="slow-instance")
    open_while_asked = []

    def ask(address, workspace_id, days, dry_run, timeout):
        open_while_asked.append(db_session.in_transaction())
        return {"workspace_id": str(workspace_id), "loaded": False, "envs": [], "removed": 0}

    retention.sweep(db_session, enforce=True, ask=ask)

    assert open_while_asked
    assert not any(open_while_asked)


def test_a_sweep_runs_without_the_lock_on_a_database_that_has_none(monkeypatch, db_session):
    monkeypatch.setattr(retention, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(retention, "instance_addresses", lambda: [])
    monkeypatch.setattr(db_session, "close", lambda: None)

    assert retention.sweep_once()["visited"] == 0


NOW = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture
def mailbox(monkeypatch):
    sent = []
    monkeypatch.setattr(retention.outbound, "configured", lambda: True)

    def deliver(to, subject, body):
        sent.append((to, body))
        return True

    monkeypatch.setattr(retention.outbound, "send", deliver)
    return sent


def test_the_owner_is_emailed_about_what_goes_next(db_session, instances, rules, mailbox):
    rules(enforce=True, warn=3)
    owner = _owner(db_session, "free")
    _workspace(db_session, owner, slug="mine")

    assert retention.warn_owners(db_session, ask=Recorder(envs=["old-run"]), now=NOW) == 1
    assert len(mailbox) == 1
    to, body = mailbox[0]
    assert to == owner.email
    assert "old-run" in body
    assert "7 days" in body


def test_an_owner_is_warned_once_per_window(db_session, instances, rules, mailbox):
    rules(enforce=True, warn=3)
    _workspace(db_session, _owner(db_session, "free"))
    ask = Recorder()

    retention.warn_owners(db_session, ask=ask, now=NOW)
    retention.warn_owners(db_session, ask=ask, now=NOW + datetime.timedelta(days=1))
    assert len(mailbox) == 1

    retention.warn_owners(db_session, ask=ask, now=NOW + datetime.timedelta(days=3))
    assert len(mailbox) == 2


def test_nobody_is_emailed_when_nothing_is_going(db_session, instances, rules, mailbox):
    rules(enforce=True)
    _workspace(db_session, _owner(db_session, "free"))
    assert retention.warn_owners(db_session, ask=Recorder(envs=[]), now=NOW) == 0
    assert retention.warn_owners(db_session, ask=lambda *args: None, now=NOW) == 0
    assert mailbox == []


def test_nobody_is_emailed_before_deleting_is_switched_on(db_session, instances, rules, mailbox):
    rules(enforce=False)
    _workspace(db_session, _owner(db_session, "free"))
    _workspace(db_session, _owner(db_session, "enterprise"), slug="forever")
    assert retention.warn_owners(db_session, ask=Recorder(), now=NOW) == 0
    assert mailbox == []


def test_a_scheduled_start_names_the_day(db_session, instances, rules, mailbox):
    rules(enforce=True, starts=NOW.date() + datetime.timedelta(days=2), warn=3)
    _workspace(db_session, _owner(db_session, "free"))
    retention.warn_owners(db_session, ask=Recorder(), now=NOW)
    assert "on 2026-10-03" in mailbox[0][1]


def test_nobody_is_emailed_while_the_start_is_further_off_than_the_warning(
    db_session, instances, rules, mailbox
):
    rules(enforce=True, starts=NOW.date() + datetime.timedelta(days=30), warn=3)
    _workspace(db_session, _owner(db_session, "free"))
    ask = Recorder()

    assert retention.warn_owners(db_session, ask=ask, now=NOW) == 0
    assert mailbox == []
    assert ask.calls == []

    soon = NOW + datetime.timedelta(days=27)
    assert retention.warn_owners(db_session, ask=ask, now=soon) == 1
    assert "on 2026-10-31" in mailbox[0][1]


def test_nobody_is_emailed_when_an_instance_did_not_answer(db_session, instances, rules, mailbox):
    rules(enforce=True, warn=3)
    workspace = _workspace(db_session, _owner(db_session, "free"))
    full = Recorder(envs=["old-run"])

    def one_silent(address, *args):
        return None if address == "visdom-2:8097" else full(address, *args)

    assert retention.warn_owners(db_session, ask=one_silent, now=NOW) == 0
    assert mailbox == []
    db_session.refresh(workspace)
    assert workspace.retention_warned_at is None


def test_no_transaction_is_open_while_warning_asks_an_instance(db_session, instances, rules, mailbox):
    rules(enforce=True, warn=3)
    _workspace(db_session, _owner(db_session, "free"))
    open_while_asked = []

    def ask(address, workspace_id, days, dry_run, timeout):
        open_while_asked.append(db_session.in_transaction())
        return {"workspace_id": str(workspace_id), "loaded": False, "envs": ["old-run"], "removed": 0}

    assert retention.warn_owners(db_session, ask=ask, now=NOW) == 1
    assert open_while_asked
    assert not any(open_while_asked)


def test_a_plan_change_lets_the_owner_be_warned_again(db_session, instances, rules, mailbox):
    rules(enforce=True, warn=3)
    owner = _owner(db_session, "free")
    workspace = _workspace(db_session, owner)

    assert retention.warn_owners(db_session, ask=Recorder(), now=NOW) == 1
    retention.forget_warnings(db_session, owner)
    db_session.commit()
    db_session.refresh(workspace)
    assert workspace.retention_warned_at is None

    later = NOW + datetime.timedelta(hours=1)
    assert retention.warn_owners(db_session, ask=Recorder(), now=later) == 1
    assert len(mailbox) == 2


def test_no_warning_is_recorded_when_email_is_not_set_up(db_session, instances, rules, monkeypatch):
    rules(enforce=True, warn=3)
    workspace = _workspace(db_session, _owner(db_session, "free"))
    monkeypatch.setattr(retention.outbound, "configured", lambda: False)

    assert retention.warn_owners(db_session, ask=Recorder(), now=NOW) == 0
    db_session.refresh(workspace)
    assert workspace.retention_warned_at is None


def test_a_failed_send_is_tried_again_on_the_next_sweep(db_session, instances, rules, monkeypatch):
    rules(enforce=True, warn=3)
    workspace = _workspace(db_session, _owner(db_session, "free"))
    attempts = []
    monkeypatch.setattr(retention.outbound, "configured", lambda: True)
    monkeypatch.setattr(retention.outbound, "send", lambda *args: attempts.append(args) and False)

    assert retention.warn_owners(db_session, ask=Recorder(), now=NOW) == 0
    db_session.refresh(workspace)
    assert workspace.retention_warned_at is None

    monkeypatch.setattr(retention.outbound, "send", lambda *args: True)
    assert retention.warn_owners(db_session, ask=Recorder(), now=NOW + datetime.timedelta(hours=1)) == 1
    db_session.refresh(workspace)
    assert workspace.retention_warned_at is not None
    assert len(attempts) == 1


def test_moving_to_another_plan_clears_the_last_warning(client, db_session, make_user, make_workspace):
    user = make_user()
    created = make_workspace(user)
    workspace = db_session.query(Workspace).filter(Workspace.id == uuid.UUID(created["id"])).first()
    workspace.retention_warned_at = NOW
    db_session.commit()

    moved = client.post("/api/v1/billing/subscription", json={"tier": "free"}, headers=user["headers"])
    assert moved.status_code == 200, moved.text

    db_session.refresh(workspace)
    assert workspace.retention_warned_at is None


class ByAge:
    """Instances that answer from the age the caller asked about.

    ``overdue`` is already past the plan window. ``soon`` is inside the warning
    window and not yet due for removal. ``silent`` is an instance that does
    not answer, which is not the same as an empty list.
    """

    def __init__(self, overdue=("overdue-run",), soon=("soon-run",), silent=None, window=7):
        self.overdue = list(overdue)
        self.soon = list(soon)
        self.silent = silent
        self.window = window
        self.calls = []

    def __call__(self, address, workspace_id, days, dry_run, timeout):
        self.calls.append({"address": address, "days": days, "dry_run": dry_run})
        if address == self.silent:
            return None
        envs = list(self.overdue)
        if days < self.window:
            envs.extend(self.soon)
        return {
            "workspace_id": str(workspace_id),
            "loaded": address == "visdom-1:8097",
            "envs": envs,
            "removed": 0 if dry_run else len(envs),
        }


def _bind_once(monkeypatch, db_session):
    """Run ``sweep_once`` against this test session instead of a new one."""
    monkeypatch.setattr(retention, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)


def _removed(ask):
    return [call for call in ask.calls if not call["dry_run"]]


def test_the_first_enforcing_pass_warns_and_does_not_delete(db_session, instances, rules, mailbox, monkeypatch):
    """Already-overdue work is named, then kept, until the warning has aged.

    Swapping the calls would still delete in this same pass. The warning has
    to be on record from earlier.
    """
    rules(enforce=True, warn=3)
    _bind_once(monkeypatch, db_session)
    workspace = _workspace(db_session, _owner(db_session, "free"), slug="first-pass")
    ask = ByAge()

    summary = retention.sweep_once(ask=ask)

    assert summary["removed"] == 0
    assert _removed(ask) == []
    assert "overdue-run" in mailbox[0][1]
    assert "soon-run" in mailbox[0][1]
    db_session.refresh(workspace)
    assert workspace.retention_warned_at is not None


def test_upcoming_environments_are_warned_and_not_removed(db_session, instances, rules, mailbox, monkeypatch):
    rules(enforce=True, warn=3)
    _bind_once(monkeypatch, db_session)
    _workspace(db_session, _owner(db_session, "free"), slug="soon-only")
    ask = ByAge(overdue=[])

    summary = retention.sweep_once(ask=ask)

    assert summary["removed"] == 0
    assert _removed(ask) == []
    body = mailbox[0][1]
    assert "soon-run" in body
    assert "overdue-run" not in body
    assert any(call["days"] < 7 for call in ask.calls)


def test_a_recent_warning_holds_overdue_environments(db_session, instances, rules, mailbox, monkeypatch):
    rules(enforce=True, warn=3)
    _bind_once(monkeypatch, db_session)
    workspace = _workspace(db_session, _owner(db_session, "free"), slug="young-warning")
    workspace.retention_warned_at = utcnow() - datetime.timedelta(days=1)
    db_session.commit()
    ask = ByAge()

    summary = retention.sweep_once(ask=ask)

    assert summary["removed"] == 0
    assert _removed(ask) == []
    assert mailbox == []


def test_overdue_environments_go_once_the_warning_is_a_full_window_old(
    db_session, instances, rules, mailbox, monkeypatch
):
    rules(enforce=True, warn=3)
    _bind_once(monkeypatch, db_session)
    workspace = _workspace(db_session, _owner(db_session, "free"), slug="aged-warning")
    workspace.retention_warned_at = utcnow() - datetime.timedelta(days=3)
    db_session.commit()
    ask = ByAge()

    summary = retention.sweep_once(ask=ask)

    assert summary["removed"] == 1
    assert _removed(ask)
    assert all(call["days"] >= 7 for call in _removed(ask))
    assert "soon-run" in mailbox[0][1]


def test_a_failed_warning_does_not_let_overdue_environments_go(db_session, instances, rules, monkeypatch):
    rules(enforce=True, warn=3)
    _bind_once(monkeypatch, db_session)
    workspace = _workspace(db_session, _owner(db_session, "free"), slug="failed-send")
    monkeypatch.setattr(retention.outbound, "configured", lambda: True)
    monkeypatch.setattr(retention.outbound, "send", lambda *args: False)
    ask = ByAge()

    summary = retention.sweep_once(ask=ask)

    assert summary["removed"] == 0
    assert _removed(ask) == []
    db_session.refresh(workspace)
    assert workspace.retention_warned_at is None


def test_clearing_the_warning_holds_the_next_deletion(db_session, instances, rules, mailbox, monkeypatch):
    """A shorter plan, or a new owner, clears the timestamp and starts grace over."""
    rules(enforce=True, warn=3)
    _bind_once(monkeypatch, db_session)
    owner = _owner(db_session, "free")
    workspace = _workspace(db_session, owner, slug="plan-changed")
    workspace.retention_warned_at = utcnow() - datetime.timedelta(days=10)
    db_session.commit()
    retention.forget_warnings(db_session, owner)
    db_session.commit()
    ask = ByAge()

    summary = retention.sweep_once(ask=ask)

    assert summary["removed"] == 0
    assert _removed(ask) == []
    assert "overdue-run" in mailbox[0][1]
    db_session.refresh(workspace)
    assert workspace.retention_warned_at is not None


def test_enforcement_still_deletes_when_email_is_not_configured(db_session, instances, rules, monkeypatch):
    rules(enforce=True, warn=3)
    _bind_once(monkeypatch, db_session)
    workspace = _workspace(db_session, _owner(db_session, "free"), slug="no-relay")
    monkeypatch.setattr(retention.outbound, "configured", lambda: False)
    ask = ByAge()

    summary = retention.sweep_once(ask=ask)

    assert summary["removed"] == 1
    assert _removed(ask)
    db_session.refresh(workspace)
    assert workspace.retention_warned_at is None


def test_a_partial_answer_does_not_warn_or_remove(db_session, instances, rules, mailbox, monkeypatch):
    rules(enforce=True, warn=3)
    _bind_once(monkeypatch, db_session)
    workspace = _workspace(db_session, _owner(db_session, "free"), slug="partial")
    ask = ByAge(silent="visdom-2:8097")

    summary = retention.sweep_once(ask=ask)

    assert summary["removed"] == 0
    assert _removed(ask) == []
    assert mailbox == []
    db_session.refresh(workspace)
    assert workspace.retention_warned_at is None


def test_a_scheduled_start_warns_ahead_and_does_not_delete_yet(db_session, instances, rules, mailbox, monkeypatch):
    starts = datetime.date.today() + datetime.timedelta(days=2)
    rules(enforce=True, starts=starts, warn=3)
    _bind_once(monkeypatch, db_session)
    _workspace(db_session, _owner(db_session, "free"), slug="scheduled")
    ask = ByAge()

    summary = retention.sweep_once(ask=ask)

    assert summary["removed"] == 0
    assert _removed(ask) == []
    assert f"on {starts.isoformat()}" in mailbox[0][1]


def test_the_first_pass_on_the_start_date_warns_instead_of_deleting(
    db_session, instances, rules, mailbox, monkeypatch
):
    rules(enforce=True, starts=datetime.date.today(), warn=3)
    _bind_once(monkeypatch, db_session)
    _workspace(db_session, _owner(db_session, "free"), slug="starts-today")
    ask = ByAge()

    summary = retention.sweep_once(ask=ask)

    assert summary["removed"] == 0
    assert _removed(ask) == []
    assert mailbox


def test_a_warning_aged_before_the_start_allows_deletion_when_it_arrives(
    db_session, instances, rules, mailbox, monkeypatch
):
    rules(enforce=True, starts=datetime.date.today(), warn=3)
    _bind_once(monkeypatch, db_session)
    workspace = _workspace(db_session, _owner(db_session, "free"), slug="start-aged")
    workspace.retention_warned_at = utcnow() - datetime.timedelta(days=3)
    db_session.commit()
    ask = ByAge()

    summary = retention.sweep_once(ask=ask)

    assert summary["removed"] == 1
    assert _removed(ask)
