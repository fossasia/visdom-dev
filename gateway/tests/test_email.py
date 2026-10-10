# Copyright 2017-present, The Visdom Authors
"""Outbound email through the configured relay, and nothing when there is none."""
import smtplib

import pytest

from app import email
from app.config import settings


class FakeRelay:
    """Records the SMTP conversation instead of having one."""

    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port
        self.calls = []
        self.sent = []
        FakeRelay.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.calls.append("send")
        self.sent.append(message)


@pytest.fixture
def relay(monkeypatch):
    FakeRelay.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeRelay)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeRelay)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp-relay.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "login@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret-key")
    monkeypatch.setattr(settings, "MAIL_FROM", "noreply@visdom.dev")
    monkeypatch.setattr(settings, "MAIL_FROM_NAME", "Visdom")
    return FakeRelay


def test_nothing_is_sent_until_a_relay_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "MAIL_FROM", "")
    FakeRelay.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeRelay)

    assert email.configured() is False
    assert email.send("someone@example.com", "Hello", "Body") is False
    assert FakeRelay.instances == []


def test_a_message_goes_out_over_starttls_with_a_login(relay):
    assert email.send("someone@example.com", "Hello", "Body text") is True

    (conversation,) = relay.instances
    assert conversation.port == 587
    assert conversation.calls == ["starttls", ("login", "login@example.com", "secret-key"), "send"]
    message = conversation.sent[0]
    assert message["From"] == "Visdom <noreply@visdom.dev>"
    assert message["To"] == "someone@example.com"
    assert message["Subject"] == "Hello"
    assert "Body text" in message.get_content()


def test_port_465_is_tls_from_the_start(relay, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_PORT", 465)
    email.send("someone@example.com", "Hello", "Body")
    assert "starttls" not in relay.instances[0].calls


def test_no_login_is_attempted_without_a_username(relay, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_USERNAME", "")
    email.send("someone@example.com", "Hello", "Body")
    assert relay.instances[0].calls == ["starttls", "send"]


def test_a_relay_failure_is_reported_not_raised(relay, monkeypatch):
    def refuse(self, message):
        raise smtplib.SMTPRecipientsRefused({"someone@example.com": (550, b"no")})

    monkeypatch.setattr(FakeRelay, "send_message", refuse)
    assert email.send("someone@example.com", "Hello", "Body") is False


def test_an_invite_is_sent_without_making_the_request_wait(monkeypatch):
    queued = []
    monkeypatch.setattr(email, "send_later", lambda *args: queued.append(args))
    email.send_workspace_invite_email("new@example.com", "Research", "https://visdom.dev")

    (to, subject, body) = queued[0]
    assert to == "new@example.com"
    assert "Research" in subject
    assert "https://visdom.dev" in body
