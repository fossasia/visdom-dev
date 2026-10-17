# Copyright 2017-present, The Visdom Authors
"""Folding the instances' live counters into durable hourly rows.

Each instance's counters are cumulative since it started, so a sample is worth
only its difference from the one before. These pin the three ways that goes
wrong: differencing a sum across instances, losing the baseline on a restart,
and more than one worker folding the same tick.
"""
import datetime

from app import usage_rollup
from app.models import UsageBaseline, WorkspaceUsageHour

A = "visdom-1:8097"
B = "visdom-2:8097"
UTC = datetime.timezone.utc


def _entry(workspace_id, writes=0, broadcasts=0, stored=0, hour=None, mask=0):
    entry = {
        "workspace_id": workspace_id,
        "writes": writes,
        "broadcasts": broadcasts,
        "broadcast_bytes": 0,
        "bytes": stored,
    }
    if hour is not None:
        entry["active_hour"] = hour
        entry["active_minutes_mask"] = mask
    return entry


def _tick(db, *answers, when=None):
    return usage_rollup.sample_once(db, lambda: list(answers), when=when)


def _epoch_hour(year, month, day, hour):
    return int(datetime.datetime(year, month, day, hour, tzinfo=UTC).timestamp() // 3600)


def _rows(db):
    return db.query(WorkspaceUsageHour).all()


def test_the_hour_bucket_is_the_top_of_the_hour():
    moment = datetime.datetime(2026, 5, 4, 13, 47, 31, 900, UTC)
    assert usage_rollup.hour_start(moment) == datetime.datetime(2026, 5, 4, 13, tzinfo=UTC)


def test_an_epoch_hour_names_the_top_of_that_hour():
    assert usage_rollup.hour_of(_epoch_hour(2026, 5, 4, 10)) == datetime.datetime(
        2026, 5, 4, 10, tzinfo=UTC
    )


def test_a_counter_is_worth_only_what_is_new():
    assert usage_rollup.counter_delta(0, 10) == 10
    assert usage_rollup.counter_delta(10, 25) == 15
    assert usage_rollup.counter_delta(10, 10) == 0


def test_one_instance_going_backwards_means_it_restarted():
    assert usage_rollup.counter_delta(500, 7) == 7


def test_a_mask_counts_the_minutes_it_marks():
    assert usage_rollup.active_minutes_from(0b1011) == 3
    assert usage_rollup.active_minutes_from((1 << 60) - 1) == 60
    assert usage_rollup.active_minutes_from(None) == 0


def test_without_postgres_the_tick_is_always_taken(db_session):
    assert usage_rollup.take_tick(db_session) is True


def test_a_workspace_seen_for_the_first_time_only_gets_a_baseline(
    client, make_user, make_workspace, db_session
):
    """There is no telling how much of a first total was banked before, so
    none of it is billed."""
    ws = make_workspace(make_user())["id"]
    _tick(db_session, (A, True, [_entry(ws, writes=100)]))

    assert _rows(db_session) == []
    baseline = db_session.get(UsageBaseline, {"instance": A, "workspace_id": ws})
    assert baseline.writes == 100


def test_the_next_sample_records_only_the_difference(
    client, make_user, make_workspace, db_session
):
    ws = make_workspace(make_user())["id"]
    _tick(db_session, (A, True, [_entry(ws, writes=100)]))
    _tick(db_session, (A, True, [_entry(ws, writes=130)]))

    assert _rows(db_session)[0].writes == 30


def test_a_gateway_restart_does_not_bill_history_again(
    client, make_user, make_workspace, db_session
):
    """The baseline is in the database, so a fresh process reading the same
    totals finds nothing new rather than the instance's whole lifetime."""
    ws = make_workspace(make_user())["id"]
    _tick(db_session, (A, True, [_entry(ws, writes=100)]))
    _tick(db_session, (A, True, [_entry(ws, writes=150)]))
    _tick(db_session, (A, True, [_entry(ws, writes=150)]))

    assert _rows(db_session)[0].writes == 50


def test_one_instance_restarting_does_not_bill_the_others_totals(
    client, make_user, make_workspace, db_session
):
    """Summed, 200 then 113 reads as a reset worth 113. Per instance it is
    only the 3 the restarted one has counted since."""
    ws = make_workspace(make_user())["id"]
    _tick(db_session, (A, True, [_entry(ws, writes=100)]), (B, True, [_entry(ws, writes=100)]))
    _tick(db_session, (A, True, [_entry(ws, writes=110)]), (B, True, [_entry(ws, writes=100)]))
    _tick(db_session, (A, True, [_entry(ws, writes=110)]), (B, True, [_entry(ws, writes=3)]))

    assert _rows(db_session)[0].writes == 13


def test_new_counts_from_different_instances_add_up(
    client, make_user, make_workspace, db_session
):
    ws = make_workspace(make_user())["id"]
    _tick(db_session, (A, True, [_entry(ws, writes=0)]), (B, True, [_entry(ws, writes=0)]))
    _tick(db_session, (A, True, [_entry(ws, writes=10)]), (B, True, [_entry(ws, writes=5)]))

    assert _rows(db_session)[0].writes == 15


def test_an_instance_that_did_not_answer_is_caught_up_when_it_does(
    client, make_user, make_workspace, db_session
):
    ws = make_workspace(make_user())["id"]
    _tick(db_session, (A, True, [_entry(ws, writes=100)]))
    _tick(db_session, (A, False, []))
    _tick(db_session, (A, True, [_entry(ws, writes=140)]))

    assert _rows(db_session)[0].writes == 40


def test_the_same_minute_on_two_instances_is_one_minute(
    client, make_user, make_workspace, db_session
):
    ws = make_workspace(make_user())["id"]
    hour = _epoch_hour(2026, 5, 4, 10)
    _tick(
        db_session,
        (A, True, [_entry(ws, hour=hour, mask=0b01)]),
        (B, True, [_entry(ws, hour=hour, mask=0b11)]),
        when=datetime.datetime(2026, 5, 4, 10, 30, tzinfo=UTC),
    )

    assert _rows(db_session)[0].active_minutes == 2


def test_active_minutes_land_on_the_hour_they_belong_to(
    client, make_user, make_workspace, db_session
):
    """A tick just after the hour turns can still carry the last hour's mask."""
    ws = make_workspace(make_user())["id"]
    _tick(
        db_session,
        (A, True, [_entry(ws, hour=_epoch_hour(2026, 5, 4, 10), mask=0b111)]),
        when=datetime.datetime(2026, 5, 4, 11, 0, 30, tzinfo=UTC),
    )

    (row,) = _rows(db_session)
    assert row.hour_start.hour == 10
    assert row.active_minutes == 3


def test_the_hour_keeps_its_highest_minute_count(
    client, make_user, make_workspace, db_session
):
    """An instance restarting mid-hour starts its mask again; that must not
    lower what the hour already has."""
    ws = make_workspace(make_user())["id"]
    hour = _epoch_hour(2026, 5, 4, 10)
    when = datetime.datetime(2026, 5, 4, 10, 30, tzinfo=UTC)
    _tick(db_session, (A, True, [_entry(ws, hour=hour, mask=0b111)]), when=when)
    _tick(db_session, (A, True, [_entry(ws, hour=hour, mask=0b1)]), when=when)

    assert _rows(db_session)[0].active_minutes == 3


def test_stored_bytes_is_the_largest_reading_not_a_sum(
    client, make_user, make_workspace, db_session
):
    ws = make_workspace(make_user())["id"]
    _tick(db_session, (A, True, [_entry(ws, stored=900)]), (B, True, [_entry(ws, stored=500)]))
    _tick(db_session, (A, True, [_entry(ws, stored=800)]))

    assert _rows(db_session)[0].peak_bytes == 900


def test_different_hours_are_different_rows(client, make_user, make_workspace, db_session):
    ws = make_workspace(make_user())["id"]
    _tick(db_session, (A, True, [_entry(ws, writes=0)]))
    _tick(
        db_session,
        (A, True, [_entry(ws, writes=4)]),
        when=datetime.datetime(2026, 5, 4, 10, 30, tzinfo=UTC),
    )
    _tick(
        db_session,
        (A, True, [_entry(ws, writes=9)]),
        when=datetime.datetime(2026, 5, 4, 11, 5, tzinfo=UTC),
    )

    assert sorted(row.writes for row in _rows(db_session)) == [4, 5]


def test_a_workspace_the_database_does_not_know_is_skipped(db_session):
    """The instances report from disk, which can outlive the row."""
    _tick(db_session, (A, True, [_entry("not-a-uuid", writes=5)]))
    _tick(db_session, (A, True, [_entry("not-a-uuid", writes=9)]))
    assert _rows(db_session) == []


def test_a_tick_that_reaches_nobody_records_nothing(db_session):
    def unreachable():
        raise OSError("no instance answered")

    assert usage_rollup.sample_once(db_session, unreachable) == 0
    assert db_session.query(UsageBaseline).count() == 0
