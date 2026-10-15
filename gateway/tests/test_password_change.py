# Copyright 2017-present, The Visdom Authors
import re

from app import email as outbound
from app import password_reset
from app.models import PasswordReset, User

AUTH = "/api/v1/auth"

def _change(client, headers, current, new):
    return client.post(
        f"{AUTH}/change-password",
        json={"current_password": current, "new_password": new},
        headers=headers,
    )

def _signs_in(client, email, password):
    return client.post(f"{AUTH}/login", data={"username": email, "password": password}).status_code == 200

def test_changing_the_password_takes_effect_on_the_next_sign_in(client, make_user):
    user = make_user()
    assert _change(client, user["headers"], user["password"], "a-better-password").status_code == 200
    assert _signs_in(client, user["email"], "a-better-password")
    assert not _signs_in(client, user["email"], user["password"])

def test_the_browser_that_changed_it_is_handed_a_working_token(client, make_user):
    user = make_user()
    changed = _change(client, user["headers"], user["password"], "a-better-password")
    fresh = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get(f"{AUTH}/me", headers=fresh).status_code == 200

def test_every_other_session_is_signed_out(client, make_user):
    user = make_user()
    _change(client, user["headers"], user["password"], "a-better-password")
    assert client.get(f"{AUTH}/me", headers=user["headers"]).status_code == 401

def test_the_current_password_has_to_be_right(client, make_user):
    user = make_user()
    refused = _change(client, user["headers"], "not-my-password", "a-better-password")
    assert refused.status_code == 400
    assert _signs_in(client, user["email"], user["password"])

def test_the_new_password_has_to_be_different(client, make_user):
    user = make_user()
    assert _change(client, user["headers"], user["password"], user["password"]).status_code == 400

def test_a_short_password_is_refused(client, make_user):
    user = make_user()
    assert _change(client, user["headers"], user["password"], "abc").status_code == 422

def test_being_signed_in_is_needed_to_change_it(client):
    anonymous = client.post(
        f"{AUTH}/change-password", json={"current_password": "x", "new_password": "yyyyyy"}
    )
    assert anonymous.status_code == 401

def test_changing_it_kills_any_reset_link_already_sent(client, db_session, make_user, monkeypatch):
    sent = []
    monkeypatch.setattr(outbound, "configured", lambda: True)
    monkeypatch.setattr(outbound, "send_later", lambda to, subject, body: sent.append(body))
    user = make_user()
    client.post(f"{AUTH}/forgot-password", json={"email": user["email"]})
    token = re.search(r"/reset-password#token=(\S+)", sent[0]).group(1)

    _change(client, user["headers"], user["password"], "a-better-password")

    refused = client.post(f"{AUTH}/reset-password", json={"token": token, "password": "another-one"})
    assert refused.status_code == 400
    assert db_session.query(PasswordReset).filter(PasswordReset.used_at.is_(None)).count() == 0

def test_spend_all_leaves_other_accounts_links_alone(db_session, make_user):
    mine = make_user()
    theirs = make_user()
    users = {u["email"]: db_session.query(User).filter(User.email == u["email"]).one() for u in (mine, theirs)}
    password_reset.issue(db_session, users[mine["email"]])
    kept = password_reset.issue(db_session, users[theirs["email"]])

    password_reset.spend_all(db_session, users[mine["email"]])
    db_session.commit()

    assert password_reset.redeem(db_session, kept, "their-new-password") is not None
