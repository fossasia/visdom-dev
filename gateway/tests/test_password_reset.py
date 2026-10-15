# Copyright 2017-present, The Visdom Authors
import datetime
import re

import pytest

from app import email as outbound
from app import password_reset
from app.models import PasswordReset, User, utcnow

AUTH = "/api/v1/auth"


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(outbound, "configured", lambda: True)
    monkeypatch.setattr(outbound, "send_later", lambda to, subject, body: sent.append((to, body)))
    return sent


def _link(body):
    return re.search(r"/reset-password#token=(\S+)", body).group(1)


def _ask(client, email):
    return client.post(f"{AUTH}/forgot-password", json={"email": email})


def _reset(client, token, password="brandnewpassword"):
    return client.post(f"{AUTH}/reset-password", json={"token": token, "password": password})


def _signs_in(client, email, password):
    return client.post(f"{AUTH}/login", data={"username": email, "password": password}).status_code == 200


def test_a_reset_link_is_emailed_and_sets_a_new_password(client, make_user, outbox):
    user = make_user()
    assert _ask(client, user["email"].upper()).status_code == 202
    assert [to for to, _ in outbox] == [user["email"]]

    assert _reset(client, _link(outbox[0][1])).status_code == 200
    assert _signs_in(client, user["email"], "brandnewpassword")
    assert not _signs_in(client, user["email"], user["password"])


def test_the_reply_is_the_same_whether_or_not_the_account_exists(client, make_user, outbox):
    user = make_user()
    known = _ask(client, user["email"])
    unknown = _ask(client, "nobody@example.com")
    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json())
    assert len(outbox) == 1


def test_resetting_signs_out_every_session(client, make_user, outbox):
    user = make_user()
    _ask(client, user["email"])
    _reset(client, _link(outbox[0][1]))
    assert client.get(f"{AUTH}/me", headers=user["headers"]).status_code == 401


def test_a_link_works_once(client, make_user, outbox):
    user = make_user()
    _ask(client, user["email"])
    token = _link(outbox[0][1])
    assert _reset(client, token).status_code == 200
    assert _reset(client, token, "yetanotherpassword").status_code == 400
    assert _signs_in(client, user["email"], "brandnewpassword")


def test_a_link_older_than_an_hour_is_refused(client, db_session, make_user):
    make_user(email="late@example.com")
    user = db_session.query(User).filter(User.email == "late@example.com").one()
    stale = password_reset.issue(db_session, user, now=utcnow() - datetime.timedelta(minutes=61))
    fresh = password_reset.issue(db_session, user, now=utcnow() - datetime.timedelta(minutes=59))
    assert _reset(client, stale).status_code == 400
    assert _reset(client, fresh).status_code == 200


def test_using_one_link_spends_the_others(client, make_user, outbox):
    user = make_user()
    _ask(client, user["email"])
    _ask(client, user["email"])
    first, second = (_link(body) for _, body in outbox)
    assert _reset(client, second).status_code == 200
    assert _reset(client, first).status_code == 400


def test_only_a_few_links_are_sent_an_hour(client, make_user, outbox):
    user = make_user()
    for _ in range(password_reset.PER_HOUR + 2):
        assert _ask(client, user["email"]).status_code == 202
    assert len(outbox) == password_reset.PER_HOUR


def test_only_a_hash_of_the_token_is_stored(client, db_session, make_user, outbox):
    user = make_user()
    _ask(client, user["email"])
    token = _link(outbox[0][1])
    stored = db_session.query(PasswordReset).one()
    assert token not in stored.token_hash
    assert len(stored.token_hash) == 64


def test_a_suspended_account_is_not_sent_a_link(client, db_session, make_user, outbox):
    user = make_user()
    record = db_session.query(User).filter(User.email == user["email"]).one()
    record.is_active = False
    db_session.commit()
    assert _ask(client, user["email"]).status_code == 202
    assert outbox == []


def test_without_email_the_reply_says_so_and_nothing_is_issued(client, db_session, make_user, monkeypatch):
    user = make_user()
    monkeypatch.setattr(outbound, "configured", lambda: False)
    reply = _ask(client, user["email"])
    assert reply.json()["email_enabled"] is False
    assert db_session.query(PasswordReset).count() == 0


def test_a_made_up_token_is_refused(client):
    assert _reset(client, "not-a-real-token").status_code == 400


def test_a_short_new_password_is_refused(client, make_user, outbox):
    user = make_user()
    _ask(client, user["email"])
    assert _reset(client, _link(outbox[0][1]), "abc").status_code == 422
