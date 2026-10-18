# Copyright 2017-present, The Visdom Authors
import io
import json

import pytest

from app import internal_signing
from app.admin import activity

ACTIVITY_SIGNATURE = "0d322e34f6824f7fc34f64a830f5bf19b82cf6ccccdf70984a68eccc1562c1a9"


def test_the_signature_matches_what_visdom_checks():
    assert (
        internal_signing.signature("test-key", "GET", "/vis/_activity", 1800000000, b"")
        == ACTIVITY_SIGNATURE
    )
    assert (
        internal_signing.signature("test-key", "POST", "/vis/_drop", 1800000000, b'{"workspace_id": "ws-a"}')
        == "56bdd87730abd4c3a545707937679b3ad3cabc131adf186a219f737b698e3ecf"
    )


def test_the_headers_carry_the_time_and_the_signature():
    headers = internal_signing.signed_headers("test-key", "GET", "/vis/_activity", now=1800000000)

    assert headers == {
        "X-Visdom-Timestamp": "1800000000",
        "X-Visdom-Signature": ACTIVITY_SIGNATURE,
    }


def test_activity_is_asked_on_the_internal_port_with_a_signature(monkeypatch):
    sent = []

    def urlopen(request, timeout, context=None):
        sent.append(request)
        return io.BytesIO(json.dumps({"workspaces": []}).encode())

    monkeypatch.setattr(activity.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(activity.settings, "VISDOM_INTERNAL_PORT", 8098)
    monkeypatch.setattr(activity.settings, "VISDOM_INTERNAL_READ_KEY", "test-key")
    monkeypatch.setattr(internal_signing.time, "time", lambda: 1800000000)

    assert activity._ask("visdom-1:8097", 1.0) == (True, [])

    request = sent[0]
    assert request.full_url == "https://visdom-1:8098/vis/_activity"
    assert request.get_header("X-visdom-timestamp") == "1800000000"
    assert request.get_header("X-visdom-signature") == ACTIVITY_SIGNATURE


def test_a_ca_path_that_is_a_directory_is_named(monkeypatch, tmp_path):
    monkeypatch.setattr(activity.settings, "VISDOM_INTERNAL_CA", str(tmp_path))

    assert activity.internal_setup_problem() == "VISDOM_INTERNAL_CA cannot be read"


@pytest.mark.parametrize(
    "setting, value, problem",
    [
        ("VISDOM_INTERNAL_READ_KEY", "", "VISDOM_INTERNAL_READ_KEY is not set"),
        ("VISDOM_INTERNAL_CA", "", "VISDOM_INTERNAL_CA is not set"),
        ("VISDOM_INTERNAL_CA", "/nowhere/ca.pem", "VISDOM_INTERNAL_CA cannot be read"),
    ],
)
def test_nothing_is_sent_until_the_key_and_ca_are_set(monkeypatch, setting, value, problem):
    sent = []
    monkeypatch.setattr(activity.urllib.request, "urlopen", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(activity.settings, setting, value)

    assert activity.internal_setup_problem() == problem
    assert activity._ask("visdom-1:8097", 1.0) == (False, [])
    assert activity.certificate_days_left("visdom-1:8097", 1.0) is None
    assert sent == []
