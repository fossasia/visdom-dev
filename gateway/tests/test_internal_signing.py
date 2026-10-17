# Copyright 2017-present, The Visdom Authors
import io
import json

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

    def urlopen(request, timeout):
        sent.append(request)
        return io.BytesIO(json.dumps({"workspaces": []}).encode())

    monkeypatch.setattr(activity.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(activity.settings, "VISDOM_INTERNAL_PORT", 8098)
    monkeypatch.setattr(activity.settings, "VISDOM_INTERNAL_READ_KEY", "test-key")
    monkeypatch.setattr(internal_signing.time, "time", lambda: 1800000000)

    assert activity._ask("visdom-1:8097", 1.0) == (True, [])

    request = sent[0]
    assert request.full_url == "http://visdom-1:8098/vis/_activity"
    assert request.get_header("X-visdom-timestamp") == "1800000000"
    assert request.get_header("X-visdom-signature") == ACTIVITY_SIGNATURE
