# Copyright 2017-present, The Visdom Authors
"""An account's own usage: active time this month and storage now."""
import datetime
import uuid

from app.models import WorkspaceUsageHour
from app.routers.usage import month_start

USAGE = "/api/v1/usage"
UTC = datetime.timezone.utc


def _hour(db, workspace_id, when, minutes=0, stored=0):
    db.add(
        WorkspaceUsageHour(
            workspace_id=uuid.UUID(workspace_id),
            hour_start=when,
            active_minutes=minutes,
            writes=0,
            broadcasts=0,
            broadcast_bytes=0,
            peak_bytes=stored,
        )
    )
    db.commit()


def _this_month(day=2, hour=10):
    return month_start().replace(day=day, hour=hour)


def test_usage_needs_a_signed_in_account(client):
    assert client.get(USAGE).status_code == 401


def test_a_new_account_has_no_usage(client, make_user):
    user = make_user()
    shown = client.get(USAGE, headers=user["headers"]).json()
    assert shown["workspaces"] == []
    assert shown["totals"] == {"active_minutes": 0, "storage_bytes": 0}


def test_active_minutes_add_up_over_the_month(client, make_user, make_workspace, db_session):
    user = make_user()
    ws = make_workspace(user)
    _hour(db_session, ws["id"], _this_month(hour=10), minutes=40)
    _hour(db_session, ws["id"], _this_month(hour=11), minutes=25)

    shown = client.get(USAGE, headers=user["headers"]).json()
    assert shown["workspaces"][0]["active_minutes"] == 65
    assert shown["totals"]["active_minutes"] == 65


def test_last_months_work_is_not_counted(client, make_user, make_workspace, db_session):
    user = make_user()
    ws = make_workspace(user)
    _hour(db_session, ws["id"], month_start() - datetime.timedelta(hours=1), minutes=60)

    assert client.get(USAGE, headers=user["headers"]).json()["totals"]["active_minutes"] == 0


def test_storage_is_the_latest_reading_not_a_sum(client, make_user, make_workspace, db_session):
    """Storage is a level; adding up a month of hourly readings would invent it."""
    user = make_user()
    ws = make_workspace(user)
    _hour(db_session, ws["id"], _this_month(hour=10), stored=500)
    _hour(db_session, ws["id"], _this_month(hour=11), stored=800)

    shown = client.get(USAGE, headers=user["headers"]).json()
    assert shown["workspaces"][0]["storage_bytes"] == 800


def test_only_workspaces_you_own_are_shown(client, make_user, make_workspace, add_member, db_session):
    """Being a member of someone else's workspace does not bill against your plan."""
    owner = make_user()
    member = make_user()
    ws = make_workspace(owner)
    add_member(owner, ws, member)
    _hour(db_session, ws["id"], _this_month(), minutes=30)

    assert client.get(USAGE, headers=member["headers"]).json()["workspaces"] == []
    assert client.get(USAGE, headers=owner["headers"]).json()["totals"]["active_minutes"] == 30


def test_the_month_starts_on_the_first_at_midnight_utc():
    moment = datetime.datetime(2026, 9, 19, 15, 42, 7, tzinfo=UTC)
    assert month_start(moment) == datetime.datetime(2026, 9, 1, tzinfo=UTC)
