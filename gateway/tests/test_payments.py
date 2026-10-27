# Copyright 2017-present, The Visdom Authors
import hashlib
import hmac
import json
import time

import pytest
import stripe
from sqlalchemy.orm import Session

from app import account_deletion, payments
from app.config import settings
from app.models import Plan, Subscription, User

BILLING = "/api/v1/billing"
WEBHOOK_SECRET = "whsec_test_secret"
PERIOD_END = 1893456000


class Found(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def to_dict(self):
        return json.loads(json.dumps(self))


class FakeStripe:
    def __init__(self):
        self.calls = []
        self.sessions = {}
        self.subscriptions = {}
        self.open_sessions = []
        self.fail = False
        self.fail_after = None
        self.busy = 0
        self.v1 = type("V1", (), {})()
        self.v1.customers = self._Section(self, "customers")
        self.v1.checkout = self._Section(self, "checkout")
        self.v1.checkout.sessions = self._Section(self, "sessions")
        self.v1.billing_portal = self._Section(self, "billing_portal")
        self.v1.billing_portal.sessions = self._Section(self, "portal")
        self.v1.subscriptions = self._Section(self, "subscriptions")

    class _Section:
        def __init__(self, owner, name):
            self.owner = owner
            self.name = name

        def create(self, params=None, options=None):
            return self.owner.act(self.name, "create", params, options)

        def retrieve(self, found_id, params=None, options=None):
            return self.owner.act(self.name, "retrieve", found_id, options)

        def update(self, found_id, params=None, options=None):
            return self.owner.act(self.name, "update", (found_id, params), options)

        def cancel(self, found_id, params=None, options=None):
            return self.owner.act(self.name, "cancel", found_id, options)

        def list(self, params=None, options=None):
            return self.owner.act(self.name, "list", params, options)

        def expire(self, found_id, params=None, options=None):
            return self.owner.act(self.name, "expire", found_id, options)

    def act(self, section, verb, args, options):
        if self.fail_after is not None:
            if self.fail_after == 0:
                raise stripe.APIConnectionError("no network")
            self.fail_after -= 1
        if self.fail:
            raise stripe.APIConnectionError("no network")
        self.calls.append((section, verb, args, options))
        if section == "customers":
            if self.busy:
                self.busy -= 1
                raise stripe.APIError("another in-progress request is using this key", http_status=409)
            return Found(id="cus_test_1")
        if section == "sessions" and verb == "create":
            self.open_sessions.append("cs_test_abc")
            return Found(id="cs_test_abc", client_secret="cs_test_abc_secret_x")
        if section == "sessions" and verb == "list":
            return Found(data=[Found(id=found_id) for found_id in self.open_sessions])
        if section == "sessions" and verb == "expire":
            self.open_sessions.remove(args)
            return Found(id=args, status="expired")
        if section == "sessions" and verb == "retrieve":
            if args not in self.sessions:
                raise stripe.InvalidRequestError("No such checkout session", "id")
            return Found(self.sessions[args])
        if section == "portal":
            return Found(url="https://billing.stripe.com/p/session/test")
        if section == "subscriptions":
            if verb in ("retrieve", "update", "cancel"):
                found_id = args[0] if verb == "update" else args
                if found_id not in self.subscriptions:
                    raise stripe.InvalidRequestError("No such subscription", "id")
                if verb != "retrieve" and self.subscriptions[found_id]["status"] == "canceled":
                    raise stripe.InvalidRequestError("A canceled subscription can only update its metadata", None)
            if verb == "retrieve":
                return Found(self.subscriptions[args])
            if verb == "list":
                found = [
                    Found(s)
                    for s in self.subscriptions.values()
                    if s["customer"] == args["customer"] and args.get("status") in ("all", s["status"])
                ]
                return Found(data=found[: args.get("limit", 10)])
            if verb == "update":
                found_id, params = args
                self.subscriptions[found_id].update(params)
                return Found(self.subscriptions[found_id])
            if verb == "cancel":
                self.subscriptions[args]["status"] = "canceled"
                return Found(self.subscriptions[args])
        raise AssertionError(f"unexpected call {section}.{verb}")


@pytest.fixture
def fake(monkeypatch, db_session):
    found = FakeStripe()
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_PUBLISHABLE_KEY", "pk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(payments, "_client_for", lambda key: found)
    db_session.get(Plan, "pro").stripe_price_id = "price_pro"
    db_session.commit()
    return found


def _subscription(sub_id="sub_1", customer="cus_test_1", status="active", price="price_pro", **extra):
    found = {
        "id": sub_id,
        "object": "subscription",
        "customer": customer,
        "status": status,
        "cancel_at_period_end": False,
        "cancel_at": None,
        "metadata": {},
        "items": {"data": [{"price": {"id": price}, "current_period_end": PERIOD_END}]},
    }
    found.update(extra)
    return found


def _signed(payload: str, secret=WEBHOOK_SECRET) -> dict:
    stamp = int(time.time())
    digest = hmac.new(secret.encode(), f"{stamp}.{payload}".encode(), hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={stamp},v1={digest}", "content-type": "application/json"}


def _send(client, kind, found, secret=WEBHOOK_SECRET):
    payload = json.dumps({"id": "evt_1", "object": "event", "type": kind, "data": {"object": found}})
    return client.post(f"{BILLING}/webhook", content=payload, headers=_signed(payload, secret))


def _account(db, user) -> User:
    db.expire_all()
    return db.query(User).filter(User.email == user["email"]).first()


def _paying(client, db, fake, user, **extra):
    record = _account(db, user)
    record.stripe_customer_id = "cus_test_1"
    db.commit()
    fake.subscriptions["sub_1"] = _subscription(**extra)
    assert _send(client, "customer.subscription.created", {"id": "sub_1"}).status_code == 200


def _plans(client):
    return {plan["id"]: plan for plan in client.get(f"{BILLING}/plans").json()}


def test_nothing_is_for_sale_without_keys(client, db_session):
    db_session.get(Plan, "pro").stripe_price_id = "price_pro"
    db_session.commit()
    assert not any(plan["checkout"] for plan in _plans(client).values())


def test_only_a_priced_plan_with_a_stripe_price_is_for_sale(client, fake):
    plans = _plans(client)
    assert plans["pro"]["checkout"] is True
    assert plans["free"]["checkout"] is False
    assert plans["enterprise"]["checkout"] is False
    assert "stripe_price_id" not in plans["pro"]


def test_checkout_is_refused_while_payments_are_off(client, make_user):
    user = make_user()
    refused = client.post(f"{BILLING}/checkout", json={"tier": "pro"}, headers=user["headers"])
    assert refused.status_code == 503


def test_checkout_needs_a_plan_with_a_price(client, make_user, fake):
    user = make_user()
    for tier in ("free", "enterprise", "platinum"):
        refused = client.post(f"{BILLING}/checkout", json={"tier": tier}, headers=user["headers"])
        assert refused.status_code == 422, tier


def test_checkout_makes_one_customer_and_an_embedded_session(client, make_user, fake, db_session):
    user = make_user()
    started = client.post(f"{BILLING}/checkout", json={"tier": "pro"}, headers=user["headers"])
    assert started.status_code == 200, started.text
    assert started.json() == {
        "session_id": "cs_test_abc",
        "client_secret": "cs_test_abc_secret_x",
        "publishable_key": "pk_test_fake",
    }
    assert _account(db_session, user).stripe_customer_id == "cus_test_1"

    client.post(f"{BILLING}/checkout", json={"tier": "pro"}, headers=user["headers"])
    assert [call[0] for call in fake.calls].count("customers") == 1

    created = [call for call in fake.calls if call[:2] == ("sessions", "create")][0][2]
    assert created["ui_mode"] == "embedded_page"
    assert created["mode"] == "subscription"
    assert created["customer"] == "cus_test_1"
    assert created["client_reference_id"] == user["id"]
    assert created["line_items"] == [{"price": "price_pro", "quantity": 1}]
    assert created["adaptive_pricing"] == {"enabled": False}
    assert created["return_url"].endswith("/?tab=billing&checkout={CHECKOUT_SESSION_ID}")


def test_a_new_checkout_closes_the_one_left_open(client, make_user, fake):
    user = make_user()
    client.post(f"{BILLING}/checkout", json={"tier": "pro"}, headers=user["headers"])
    again = client.post(f"{BILLING}/checkout", json={"tier": "pro"}, headers=user["headers"])

    assert again.status_code == 200
    assert ("sessions", "expire", "cs_test_abc", None) in fake.calls
    assert fake.open_sessions == ["cs_test_abc"]


def test_checkout_is_refused_when_stripe_already_has_a_paid_plan(client, make_user, fake, db_session):
    user = make_user()
    _account(db_session, user).stripe_customer_id = "cus_test_1"
    db_session.commit()
    fake.subscriptions["sub_1"] = _subscription()

    refused = client.post(f"{BILLING}/checkout", json={"tier": "pro"}, headers=user["headers"])

    assert refused.status_code == 409
    assert not [call for call in fake.calls if call[:2] == ("sessions", "create")]
    assert db_session.get(Subscription, "sub_1").status == "active"
    assert _account(db_session, user).tier == "pro"


def test_checkout_finds_a_paid_plan_behind_many_ended_ones(client, make_user, fake, db_session):
    user = make_user()
    _account(db_session, user).stripe_customer_id = "cus_test_1"
    db_session.commit()
    for n in range(25):
        fake.subscriptions[f"sub_old_{n}"] = _subscription(f"sub_old_{n}", status="canceled")
    fake.subscriptions["sub_1"] = _subscription(status="past_due")

    refused = client.post(f"{BILLING}/checkout", json={"tier": "pro"}, headers=user["headers"])

    assert refused.status_code == 409
    assert not [call for call in fake.calls if call[:2] == ("sessions", "create")]


def test_checkout_waits_for_a_customer_another_request_is_making(client, make_user, fake, db_session, monkeypatch):
    monkeypatch.setattr(payments, "CUSTOMER_WAIT_SECONDS", 0)
    user = make_user()
    fake.busy = 2
    started = client.post(f"{BILLING}/checkout", json={"tier": "pro"}, headers=user["headers"])

    assert started.status_code == 200
    assert [call[:2] for call in fake.calls].count(("customers", "create")) == 3
    assert _account(db_session, user).stripe_customer_id == "cus_test_1"


def test_checkout_reports_an_unreachable_provider(client, make_user, fake):
    user = make_user()
    fake.fail = True
    refused = client.post(f"{BILLING}/checkout", json={"tier": "pro"}, headers=user["headers"])
    assert refused.status_code == 502


def test_a_webhook_without_a_valid_signature_is_refused(client, fake):
    fake.subscriptions["sub_1"] = _subscription()
    assert _send(client, "customer.subscription.created", {"id": "sub_1"}, secret="whsec_wrong").status_code == 400
    unsigned = client.post(f"{BILLING}/webhook", content=b"{}")
    assert unsigned.status_code == 400
    assert not [call for call in fake.calls if call[0] == "subscriptions"]


def test_a_webhook_is_refused_while_payments_are_off(client):
    assert client.post(f"{BILLING}/webhook", content=b"{}").status_code == 503


def test_a_paid_subscription_moves_the_account_onto_its_plan(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)

    assert _account(db_session, user).tier == "pro"
    shown = client.get(f"{BILLING}/subscription", headers=user["headers"]).json()
    assert shown["tier"] == "pro"
    assert shown["usage"]["workspaces"]["limit"] == 10
    assert shown["billing"]["status"] == "active"
    assert shown["billing"]["renews_at"].startswith("2030-01-01")
    assert shown["billing"]["ends_at"] is None
    assert shown["billing"]["can_manage"] is True


def test_a_subscription_another_request_wrote_meanwhile_is_updated(client, make_user, fake, db_session, monkeypatch):
    user = make_user()
    _paying(client, db_session, fake, user)
    fake.subscriptions["sub_1"] = _subscription(status="past_due")
    real_get = Session.get
    missed = []

    def late_get(self, entity, ident, **kwargs):
        if entity is Subscription and not missed:
            missed.append(ident)
            return None
        return real_get(self, entity, ident, **kwargs)

    monkeypatch.setattr(Session, "get", late_get)
    assert _send(client, "customer.subscription.updated", {"id": "sub_1"}).status_code == 200
    monkeypatch.undo()

    assert missed == ["sub_1"]
    account = _account(db_session, user)
    rows = db_session.query(Subscription).filter(Subscription.user_id == account.id).all()
    assert [(row.id, row.status) for row in rows] == [("sub_1", "past_due")]
    assert account.tier == "pro"


def test_the_webhook_reads_the_subscription_from_stripe_not_the_event(client, make_user, fake, db_session):
    user = make_user()
    record = _account(db_session, user)
    record.stripe_customer_id = "cus_test_1"
    db_session.commit()
    fake.subscriptions["sub_1"] = _subscription(status="incomplete")

    forged = _subscription(status="active")
    assert _send(client, "customer.subscription.updated", forged).status_code == 200
    assert _account(db_session, user).tier == "free"


def test_a_cancelled_renewal_keeps_the_plan_until_it_ends(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    fake.subscriptions["sub_1"]["cancel_at_period_end"] = True
    _send(client, "customer.subscription.updated", {"id": "sub_1"})

    shown = client.get(f"{BILLING}/subscription", headers=user["headers"]).json()
    assert shown["tier"] == "pro"
    assert shown["billing"]["ends_at"].startswith("2030-01-01")
    assert shown["billing"]["renews_at"] is None


def test_a_failed_payment_keeps_the_plan_while_stripe_retries(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    fake.subscriptions["sub_1"]["status"] = "past_due"
    _send(client, "customer.subscription.updated", {"id": "sub_1"})
    assert _account(db_session, user).tier == "pro"


@pytest.mark.parametrize("status", ["canceled", "unpaid", "incomplete_expired", "paused"])
def test_an_ended_subscription_returns_the_account_to_free(client, make_user, fake, db_session, status):
    user = make_user()
    _paying(client, db_session, fake, user)
    fake.subscriptions["sub_1"]["status"] = status
    _send(client, "customer.subscription.deleted", {"id": "sub_1"})
    assert _account(db_session, user).tier == "free"


def test_an_ended_subscription_leaves_a_plan_staff_gave(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    record = _account(db_session, user)
    record.tier = "enterprise"
    db_session.commit()
    fake.subscriptions["sub_1"]["status"] = "canceled"
    _send(client, "customer.subscription.deleted", {"id": "sub_1"})
    assert _account(db_session, user).tier == "enterprise"


def test_a_subscription_for_someone_unknown_changes_nothing(client, make_user, fake, db_session):
    user = make_user()
    fake.subscriptions["sub_9"] = _subscription(sub_id="sub_9", customer="cus_other")
    assert _send(client, "customer.subscription.created", {"id": "sub_9"}).status_code == 200
    assert _account(db_session, user).tier == "free"
    assert db_session.query(Subscription).count() == 0


def test_metadata_cannot_claim_an_account_with_another_customer(client, make_user, fake, db_session):
    user = make_user()
    record = _account(db_session, user)
    record.stripe_customer_id = "cus_real"
    db_session.commit()
    fake.subscriptions["sub_9"] = _subscription(
        sub_id="sub_9", customer="cus_other", metadata={"user_id": user["id"]}
    )
    _send(client, "customer.subscription.created", {"id": "sub_9"})
    assert _account(db_session, user).tier == "free"


def test_a_price_no_plan_uses_changes_no_plan(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user, price="price_unknown")
    assert _account(db_session, user).tier == "free"


def test_a_completed_checkout_brings_its_subscription_in(client, make_user, fake, db_session):
    user = make_user()
    record = _account(db_session, user)
    record.stripe_customer_id = "cus_test_1"
    db_session.commit()
    fake.subscriptions["sub_1"] = _subscription()
    completed = {"id": "cs_test_abc", "object": "checkout.session", "mode": "subscription", "subscription": "sub_1"}
    assert _send(client, "checkout.session.completed", completed).status_code == 200
    assert _account(db_session, user).tier == "pro"


def test_returning_from_checkout_settles_the_plan(client, make_user, fake, db_session):
    user = make_user()
    record = _account(db_session, user)
    record.stripe_customer_id = "cus_test_1"
    db_session.commit()
    fake.subscriptions["sub_1"] = _subscription()
    fake.sessions["cs_test_abc"] = {
        "id": "cs_test_abc",
        "status": "complete",
        "client_reference_id": user["id"],
        "subscription": "sub_1",
    }
    found = client.get(f"{BILLING}/checkout/cs_test_abc", headers=user["headers"])
    assert found.status_code == 200, found.text
    assert found.json()["status"] == "complete"
    assert found.json()["subscription"]["tier"] == "pro"


def test_someone_elses_checkout_is_not_found(client, make_user, fake):
    owner = make_user()
    other = make_user()
    fake.sessions["cs_test_abc"] = {"id": "cs_test_abc", "status": "complete", "client_reference_id": owner["id"]}
    assert client.get(f"{BILLING}/checkout/cs_test_abc", headers=other["headers"]).status_code == 404
    assert client.get(f"{BILLING}/checkout/cs_test_missing", headers=owner["headers"]).status_code == 404
    assert client.get(f"{BILLING}/checkout/not-a-session", headers=owner["headers"]).status_code == 404


def test_a_paying_account_changes_plan_through_the_portal(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    again = client.post(f"{BILLING}/checkout", json={"tier": "pro"}, headers=user["headers"])
    assert again.status_code == 409
    to_free = client.post(f"{BILLING}/subscription", json={"tier": "free"}, headers=user["headers"])
    assert to_free.status_code == 409
    portal = client.post(f"{BILLING}/portal", headers=user["headers"])
    assert portal.json() == {"url": "https://billing.stripe.com/p/session/test"}


def test_the_portal_needs_a_billing_account(client, make_user, fake):
    user = make_user()
    assert client.post(f"{BILLING}/portal", headers=user["headers"]).status_code == 409


def test_manage_billing_needs_a_subscription(client, make_user, fake, db_session):
    user = make_user()
    record = _account(db_session, user)
    record.stripe_customer_id = "cus_test_1"
    db_session.commit()

    shown = client.get(f"{BILLING}/subscription", headers=user["headers"]).json()
    assert shown["billing"]["can_manage"] is False
    assert client.post(f"{BILLING}/portal", headers=user["headers"]).status_code == 409


def test_the_deletion_preview_names_a_plan_that_will_stop_renewing(client, make_user, fake, db_session):
    user = make_user()
    assert client.get("/api/v1/auth/me/deletion", headers=user["headers"]).json()["renewing_plan"] is None
    _paying(client, db_session, fake, user)
    assert client.get("/api/v1/auth/me/deletion", headers=user["headers"]).json()["renewing_plan"] == "Pro"

    fake.subscriptions["sub_1"]["cancel_at_period_end"] = True
    _send(client, "customer.subscription.updated", {"id": "sub_1"})
    assert client.get("/api/v1/auth/me/deletion", headers=user["headers"]).json()["renewing_plan"] is None


def test_renewal_stopped_by_a_deletion_can_be_turned_back_on(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    client.post("/api/v1/auth/me/deletion", json={"password": user["password"]}, headers=user["headers"])
    signed_in = client.post("/api/v1/auth/login", data={"username": user["email"], "password": user["password"]})
    assert signed_in.json()["deletion_cancelled"] is True
    headers = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}

    resumed = client.post(f"{BILLING}/renewal", headers=headers)
    assert resumed.status_code == 200, resumed.text
    assert fake.subscriptions["sub_1"]["cancel_at_period_end"] is False
    assert resumed.json()["billing"]["ends_at"] is None
    assert resumed.json()["billing"]["renews_at"].startswith("2030-01-01")
    assert client.post(f"{BILLING}/renewal", headers=headers).status_code == 409


def test_renewal_needs_a_paid_plan(client, make_user, fake):
    user = make_user()
    assert client.post(f"{BILLING}/renewal", headers=user["headers"]).status_code == 409


def test_asking_to_delete_the_account_stops_the_renewal(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    asked = client.post("/api/v1/auth/me/deletion", json={"password": user["password"]}, headers=user["headers"])
    assert asked.status_code == 202, asked.text
    assert fake.subscriptions["sub_1"]["cancel_at_period_end"] is True
    assert db_session.get(Subscription, "sub_1").ends_at is not None


def test_a_checkout_finished_after_asking_to_delete_does_not_renew(client, make_user, fake, db_session):
    user = make_user()
    _account(db_session, user).stripe_customer_id = "cus_test_1"
    db_session.commit()
    asked = client.post("/api/v1/auth/me/deletion", json={"password": user["password"]}, headers=user["headers"])
    assert asked.status_code == 202, asked.text

    fake.subscriptions["sub_1"] = _subscription()
    assert _send(client, "customer.subscription.created", {"id": "sub_1"}).status_code == 200

    assert fake.subscriptions["sub_1"]["cancel_at_period_end"] is True
    assert db_session.get(Subscription, "sub_1").ends_at is not None


def test_nothing_is_for_sale_without_a_webhook_secret(client, fake, monkeypatch):
    assert payments.setup_gap() is None
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")

    assert "STRIPE_WEBHOOK_SECRET" in payments.setup_gap()
    assert not any(plan["checkout"] for plan in _plans(client).values())


def test_a_renewal_stopped_before_stripe_failed_is_kept(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    fake.subscriptions["sub_2"] = _subscription("sub_2")
    assert _send(client, "customer.subscription.created", {"id": "sub_2"}).status_code == 200
    fake.fail_after = 1

    asked = client.post("/api/v1/auth/me/deletion", json={"password": user["password"]}, headers=user["headers"])

    assert asked.status_code == 502
    db_session.expire_all()
    stopped = [sid for sid in ("sub_1", "sub_2") if fake.subscriptions[sid]["cancel_at_period_end"]]
    assert len(stopped) == 1
    assert db_session.get(Subscription, stopped[0]).ends_at is not None
    assert _account(db_session, user).deletion_requested_at is None


def test_deletion_is_not_started_when_the_plan_cannot_be_stopped(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    fake.fail = True
    asked = client.post("/api/v1/auth/me/deletion", json={"password": user["password"]}, headers=user["headers"])
    assert asked.status_code == 502
    assert _account(db_session, user).deletion_requested_at is None


def test_removing_the_account_cancels_the_plan_first(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    record = _account(db_session, user)
    account_deletion.remove(db_session, record, "test")
    assert fake.subscriptions["sub_1"]["status"] == "canceled"
    assert db_session.query(User).filter(User.email == user["email"]).first() is None
    assert db_session.query(Subscription).count() == 0


def test_a_plan_stripe_already_ended_does_not_hold_up_a_deletion(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    fake.subscriptions["sub_1"]["status"] = "canceled"

    asked = client.post("/api/v1/auth/me/deletion", json={"password": user["password"]}, headers=user["headers"])

    assert asked.status_code == 202, asked.text
    db_session.expire_all()
    assert db_session.get(Subscription, "sub_1").status == "canceled"
    assert _account(db_session, user).tier == "free"


def test_a_plan_stripe_no_longer_knows_does_not_hold_up_a_deletion(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    del fake.subscriptions["sub_1"]

    asked = client.post("/api/v1/auth/me/deletion", json={"password": user["password"]}, headers=user["headers"])

    assert asked.status_code == 202, asked.text
    db_session.expire_all()
    assert db_session.get(Subscription, "sub_1").status == "canceled"


def test_an_account_whose_plan_stripe_already_ended_is_removed(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    fake.subscriptions["sub_1"]["status"] = "canceled"

    account_deletion.remove(db_session, _account(db_session, user), "test")

    assert db_session.query(User).filter(User.email == user["email"]).first() is None


def test_an_account_whose_plan_cannot_be_cancelled_is_kept(client, make_user, fake, db_session):
    user = make_user()
    _paying(client, db_session, fake, user)
    fake.fail = True
    with pytest.raises(payments.PaymentsDown):
        account_deletion.remove(db_session, _account(db_session, user), "test")
    assert _account(db_session, user) is not None
    assert db_session.get(Subscription, "sub_1").status == "active"
