# Copyright 2017-present, The Visdom Authors
"""The health endpoints, which are what an uptime check reads.

A check that answers 200 while the product is unusable is worse than no check,
so these are about what each one refuses to call healthy.
"""

from app.routers import health

HEALTH = "/api/v1/health"


def test_the_cheap_check_says_the_database_is_reachable(client):
    answered = client.get(HEALTH)
    assert answered.status_code == 200
    assert answered.json()["database"] == "connected"


def test_the_cheap_check_does_not_hand_out_the_drivers_error(client, monkeypatch):
    """A public endpoint, and a driver's message names the host and the user."""

    def explode(*args, **kwargs):
        raise RuntimeError("connection to server at 10.0.0.4, user visdom failed")

    monkeypatch.setattr("app.routers.health.text", explode)
    refused = client.get(HEALTH)
    assert refused.status_code == 503
    assert "visdom" not in refused.text
    assert "10.0.0.4" not in refused.text


def test_every_instance_answering_is_healthy(client, monkeypatch):
    monkeypatch.setattr(health, "instance_addresses", lambda: ["visdom-1:8097", "visdom-2:8097"])
    monkeypatch.setattr(
        health, "activity_per_instance", lambda timeout: [("visdom-1:8097", True, []), ("visdom-2:8097", True, [])]
    )
    monkeypatch.setattr(health, "certificate_days_left", lambda address, timeout: 400.5)
    answered = client.get(f"{HEALTH}/components")
    assert answered.status_code == 200
    assert answered.json() == {
        "status": "healthy",
        "checks": {
            "database": "ok",
            "visdom": "2 of 2 answering",
            "internal_certificate": "400 days left",
            "metering": "off",
        },
    }


def test_an_internal_certificate_near_its_end_is_degraded(client, monkeypatch):
    monkeypatch.setattr(health, "instance_addresses", lambda: ["visdom-1:8097", "visdom-2:8097"])
    monkeypatch.setattr(
        health, "activity_per_instance", lambda timeout: [("visdom-1:8097", True, []), ("visdom-2:8097", True, [])]
    )
    days = {"visdom-1:8097": 400.0, "visdom-2:8097": 12.0}
    monkeypatch.setattr(health, "certificate_days_left", lambda address, timeout: days[address])
    answered = client.get(f"{HEALTH}/components")
    assert answered.status_code == 503
    assert answered.json()["checks"]["internal_certificate"] == "12 days left"


def test_an_unreadable_internal_certificate_is_degraded(client, monkeypatch):
    monkeypatch.setattr(health, "instance_addresses", lambda: ["visdom-1:8097", "visdom-2:8097"])
    monkeypatch.setattr(
        health, "activity_per_instance", lambda timeout: [("visdom-1:8097", True, []), ("visdom-2:8097", True, [])]
    )
    days = {"visdom-1:8097": 400.0, "visdom-2:8097": None}
    monkeypatch.setattr(health, "certificate_days_left", lambda address, timeout: days[address])
    answered = client.get(f"{HEALTH}/components")
    assert answered.status_code == 503
    assert answered.json()["checks"]["internal_certificate"] == "could not be read on 1 of 2"


def test_a_missing_internal_key_is_named_and_degraded(client, monkeypatch):
    monkeypatch.setattr(health, "instance_addresses", lambda: ["visdom-1:8097"])
    monkeypatch.setattr(health, "activity_per_instance", lambda timeout: [("visdom-1:8097", False, [])])
    monkeypatch.setattr(health, "certificate_days_left", lambda address, timeout: None)
    monkeypatch.setattr(health.settings, "VISDOM_INTERNAL_READ_KEY", "")
    answered = client.get(f"{HEALTH}/components")
    assert answered.status_code == 503
    assert answered.json()["checks"]["internal_setup"] == "VISDOM_INTERNAL_READ_KEY is not set"


def test_one_instance_down_is_degraded(client, monkeypatch):
    """The failure this exists for: the console is fine and no plots work."""
    monkeypatch.setattr(health, "instance_addresses", lambda: ["visdom-1:8097", "visdom-2:8097"])
    monkeypatch.setattr(
        health, "activity_per_instance", lambda timeout: [("visdom-1:8097", True, []), ("visdom-2:8097", False, [])]
    )
    monkeypatch.setattr(health, "certificate_days_left", lambda address, timeout: None)
    answered = client.get(f"{HEALTH}/components")
    assert answered.status_code == 503
    assert answered.json()["status"] == "degraded"
    assert answered.json()["checks"]["visdom"] == "1 of 2 answering"


def test_a_deployment_with_no_instances_configured_is_not_called_broken(client, monkeypatch):
    monkeypatch.setattr(health, "instance_addresses", lambda: [])
    answered = client.get(f"{HEALTH}/components")
    assert answered.status_code == 200
    assert answered.json()["checks"]["visdom"] == "no instances configured"


def _metered(monkeypatch, seconds=60):
    monkeypatch.setattr(health, "instance_addresses", lambda: [])
    monkeypatch.setattr(health.settings, "USAGE_SAMPLE_SECONDS", seconds)


def test_metering_that_just_ran_is_healthy(client, db_session, monkeypatch):
    from app import heartbeat

    _metered(monkeypatch)
    heartbeat.mark(db_session, heartbeat.USAGE)
    db_session.commit()

    answered = client.get(f"{HEALTH}/components")
    assert answered.status_code == 200
    assert answered.json()["checks"]["metering"] == "ok"


def test_metering_that_has_stopped_is_degraded(client, db_session, monkeypatch):
    """Nothing else notices: no usage rows look the same as a quiet hour."""
    import datetime

    from app import heartbeat
    from app.models import utcnow

    _metered(monkeypatch)
    heartbeat.mark(db_session, heartbeat.USAGE, utcnow() - datetime.timedelta(minutes=20))
    db_session.commit()

    answered = client.get(f"{HEALTH}/components")
    assert answered.status_code == 503
    assert answered.json()["status"] == "degraded"
    assert answered.json()["checks"]["metering"] == "last ran 20 minutes ago"


def test_a_restart_is_given_time_before_metering_counts_as_stopped(client, monkeypatch):
    from app import heartbeat
    from app.models import utcnow

    _metered(monkeypatch)
    monkeypatch.setattr(heartbeat, "STARTED", utcnow())

    answered = client.get(f"{HEALTH}/components")
    assert answered.status_code == 200
    assert answered.json()["checks"]["metering"] == "waiting for the first run"


def test_metering_that_never_started_is_degraded(client, monkeypatch):
    import datetime

    from app import heartbeat
    from app.models import utcnow

    _metered(monkeypatch)
    monkeypatch.setattr(heartbeat, "STARTED", utcnow() - datetime.timedelta(hours=1))

    answered = client.get(f"{HEALTH}/components")
    assert answered.status_code == 503
    assert answered.json()["checks"]["metering"] == "has never run"


def test_a_sample_leaves_a_heartbeat_even_with_nothing_to_record(db_session):
    from app import heartbeat, usage_rollup

    assert heartbeat.last(db_session, heartbeat.USAGE) is None
    usage_rollup.sample_once(db_session, lambda: [])
    assert heartbeat.last(db_session, heartbeat.USAGE) is not None
