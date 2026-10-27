# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import datetime
import functools
import logging
import re
import time
import uuid

import stripe
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing import DEFAULT_TIER
from app.config import settings
from app.models import Plan, Subscription, User, utcnow

LIVE = ("active", "trialing", "past_due")
ENDED = ("canceled", "incomplete_expired")

SUBSCRIPTION_EVENTS = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.paused",
    "customer.subscription.resumed",
}

CHECKOUT_ID = re.compile(r"^cs_(test|live)_[A-Za-z0-9]{1,200}$")
PRICE_ID = re.compile(r"^price_[A-Za-z0-9]{1,200}$")

CUSTOMER_TRIES = 5
CUSTOMER_WAIT_SECONDS = 0.5


class PaymentsOff(RuntimeError):
    pass


class PaymentsDown(RuntimeError):
    pass


class AlreadyPaying(RuntimeError):
    pass


def _keys_set() -> bool:
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PUBLISHABLE_KEY)


def enabled() -> bool:
    return _keys_set() and bool(settings.STRIPE_WEBHOOK_SECRET)


def setup_gap() -> str | None:
    if _keys_set() and not settings.STRIPE_WEBHOOK_SECRET:
        return "The Stripe keys are set but STRIPE_WEBHOOK_SECRET is not, so payments stay off"
    return None


@functools.lru_cache(maxsize=1)
def _client_for(key: str) -> stripe.StripeClient:
    return stripe.StripeClient(key)


def _client() -> stripe.StripeClient:
    if not enabled():
        raise PaymentsOff("Payments are not set up yet.")
    return _client_for(settings.STRIPE_SECRET_KEY)


def _call(make):
    try:
        return make(_client().v1)
    except stripe.StripeError as exc:
        logging.warning("stripe call failed: %s", exc)
        raise PaymentsDown("The payment provider could not be reached. Try again shortly.") from exc


def _plain(found) -> dict:
    return found.to_dict() if hasattr(found, "to_dict") else dict(found)


def _billing_page() -> str:
    return settings.FRONTEND_URL.rstrip("/") + "/?tab=billing"


def _moment(seconds):
    if not seconds:
        return None
    return datetime.datetime.fromtimestamp(int(seconds), tz=datetime.timezone.utc)


def buyable(plan: dict) -> bool:
    return enabled() and bool(plan.get("price")) and bool(plan.get("stripe_price_id"))


def current(db: Session, user: User) -> Subscription | None:
    return (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id, Subscription.status.in_(LIVE))
        .order_by(Subscription.updated_at.desc())
        .first()
    )


def customer_for(db: Session, user: User) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = _call(lambda v1: _new_customer(v1, user))
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id


def _new_customer(v1, user: User):
    for attempt in range(CUSTOMER_TRIES):
        try:
            return v1.customers.create(
                params={"email": user.email, "metadata": {"user_id": str(user.id)}},
                options={"idempotency_key": f"customer-{user.id}"},
            )
        except stripe.APIError as exc:
            if exc.http_status != 409 or attempt == CUSTOMER_TRIES - 1:
                raise
            time.sleep(CUSTOMER_WAIT_SECONDS)


def start_checkout(db: Session, user: User, plan: Plan) -> dict:
    customer = customer_for(db, user)
    db.query(User).filter(User.id == user.id).with_for_update().populate_existing().first()
    for status in LIVE:
        held = _call(
            lambda v1, wanted=status: v1.subscriptions.list(params={"customer": customer, "status": wanted, "limit": 1})
        )
        if held.data:
            record(db, _plain(held.data[0]))
            raise AlreadyPaying("You already have a paid plan. Change it from Manage billing.")
    left_open = _call(
        lambda v1: v1.checkout.sessions.list(params={"customer": customer, "status": "open", "limit": 20})
    )
    for stale in left_open.data:
        _call(lambda v1, sid=stale.id: v1.checkout.sessions.expire(sid))
    tags = {"user_id": str(user.id), "plan_id": plan.id}
    session = _call(
        lambda v1: v1.checkout.sessions.create(
            params={
                "mode": "subscription",
                "ui_mode": "embedded_page",
                "customer": customer,
                "client_reference_id": str(user.id),
                "line_items": [{"price": plan.stripe_price_id, "quantity": 1}],
                "adaptive_pricing": {"enabled": False},
                "metadata": tags,
                "subscription_data": {"metadata": tags},
                "redirect_on_completion": "if_required",
                "return_url": _billing_page() + "&checkout={CHECKOUT_SESSION_ID}",
            }
        )
    )
    return {"session_id": session.id, "client_secret": session.client_secret}


def checkout_for(user: User, session_id: str) -> dict | None:
    if not CHECKOUT_ID.match(session_id or ""):
        return None
    try:
        found = _plain(_client().v1.checkout.sessions.retrieve(session_id))
    except stripe.InvalidRequestError:
        return None
    except stripe.StripeError as exc:
        logging.warning("stripe call failed: %s", exc)
        raise PaymentsDown("The payment provider could not be reached. Try again shortly.") from exc
    if found.get("client_reference_id") != str(user.id):
        return None
    return found


def portal_url(user: User) -> str:
    session = _call(
        lambda v1: v1.billing_portal.sessions.create(
            params={"customer": user.stripe_customer_id, "return_url": _billing_page()}
        )
    )
    return session.url


def read_event(payload: bytes, signature: str | None) -> dict:
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise PaymentsOff("Payments are not set up yet.")
    event = stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
    return _plain(event)


def handle(db: Session, event: dict) -> None:
    kind = event.get("type")
    found = (event.get("data") or {}).get("object") or {}
    if kind == "checkout.session.completed":
        if found.get("mode") == "subscription" and found.get("subscription"):
            sync(db, found["subscription"])
    elif kind in SUBSCRIPTION_EVENTS:
        sync(db, found["id"])


def sync(db: Session, subscription_id: str) -> Subscription | None:
    found = _call(lambda v1: v1.subscriptions.retrieve(subscription_id))
    return record(db, _plain(found))


def _owner(db: Session, found: dict) -> User | None:
    customer = found.get("customer")
    if isinstance(customer, dict):
        customer = customer.get("id")
    user = None
    if customer:
        user = db.query(User).filter(User.stripe_customer_id == customer).first()
    if user is None:
        user_id = (found.get("metadata") or {}).get("user_id")
        try:
            user = db.get(User, uuid.UUID(str(user_id))) if user_id else None
        except (TypeError, ValueError):
            user = None
        if user is not None and user.stripe_customer_id not in (None, customer):
            return None
        if user is not None and customer:
            user.stripe_customer_id = customer
    return user


def record(db: Session, found: dict) -> Subscription | None:
    user = _owner(db, found)
    if user is None:
        logging.warning("subscription %s belongs to no account here", found.get("id"))
        return None
    items = (found.get("items") or {}).get("data") or []
    first = items[0] if items else {}
    price = (first.get("price") or {}).get("id")
    plan = db.query(Plan).filter(Plan.stripe_price_id == price).first() if price else None
    if price and plan is None:
        logging.warning("subscription %s is for price %s, which no plan uses", found.get("id"), price)

    period_end = _moment(first.get("current_period_end") or found.get("current_period_end"))
    fields = {
        "plan_id": plan.id if plan else None,
        "price_id": price,
        "status": found.get("status") or "incomplete",
        "current_period_end": period_end,
        "ends_at": _moment(found.get("cancel_at")) or (period_end if found.get("cancel_at_period_end") else None),
        "updated_at": utcnow(),
    }
    row = _write(db, found["id"], user, fields)
    if user.deletion_requested_at is not None and row.status in LIVE and row.ends_at is None:
        _call(lambda v1: v1.subscriptions.update(row.id, params={"cancel_at_period_end": True}))
        row.ends_at = row.current_period_end
    settle_tier(db, user)
    db.commit()
    return row


def _write(db: Session, subscription_id: str, user: User, fields: dict) -> Subscription:
    row = db.get(Subscription, subscription_id, with_for_update=True)
    if row is None:
        try:
            with db.begin_nested():
                row = Subscription(id=subscription_id, user_id=user.id, **fields)
                db.add(row)
            return row
        except IntegrityError:
            row = db.get(Subscription, subscription_id, with_for_update=True, populate_existing=True)
    for name, value in fields.items():
        setattr(row, name, value)
    db.flush()
    return row


def settle_tier(db: Session, user: User) -> None:
    live = (
        db.query(Subscription)
        .filter(
            Subscription.user_id == user.id,
            Subscription.status.in_(LIVE),
            Subscription.plan_id.isnot(None),
        )
        .order_by(Subscription.updated_at.desc())
        .first()
    )
    if live is not None:
        user.tier = live.plan_id
        return
    paid = {
        plan_id
        for (plan_id,) in db.query(Subscription.plan_id).filter(Subscription.user_id == user.id)
        if plan_id
    }
    if user.tier in paid:
        user.tier = DEFAULT_TIER


def has_subscribed(db: Session, user: User) -> bool:
    return db.query(Subscription.id).filter(Subscription.user_id == user.id).first() is not None


def resume_renewing(db: Session, user: User) -> Subscription | None:
    row = current(db, user)
    if row is None or row.ends_at is None:
        return None
    found = _call(lambda v1: v1.subscriptions.update(row.id, params={"cancel_at_period_end": False}))
    return record(db, _plain(found))


def _ended_at_stripe(db: Session, user: User, row: Subscription) -> bool:
    try:
        found = _plain(_client().v1.subscriptions.retrieve(row.id))
    except stripe.InvalidRequestError:
        row.status = "canceled"
        row.ends_at = utcnow()
        settle_tier(db, user)
        db.commit()
        return True
    except stripe.StripeError as exc:
        logging.warning("stripe call failed: %s", exc)
        raise PaymentsDown("The payment provider could not be reached. Try again shortly.") from exc
    if found.get("status") not in ENDED:
        return False
    record(db, found)
    return True


def _change(db: Session, user: User, row: Subscription, make) -> bool:
    try:
        make(_client().v1)
    except stripe.InvalidRequestError as exc:
        if _ended_at_stripe(db, user, row):
            return False
        logging.warning("stripe call failed: %s", exc)
        raise PaymentsDown("The payment provider could not be reached. Try again shortly.") from exc
    except stripe.StripeError as exc:
        logging.warning("stripe call failed: %s", exc)
        raise PaymentsDown("The payment provider could not be reached. Try again shortly.") from exc
    return True


def stop_renewing(db: Session, user: User) -> None:
    for row in _open(db, user):
        if _change(
            db, user, row, lambda v1, sid=row.id: v1.subscriptions.update(sid, params={"cancel_at_period_end": True})
        ):
            row.ends_at = row.current_period_end
            db.commit()


def end_now(db: Session, user: User) -> None:
    for row in _open(db, user):
        if _change(db, user, row, lambda v1, sid=row.id: v1.subscriptions.cancel(sid)):
            row.status = "canceled"
            row.ends_at = utcnow()


def _open(db: Session, user: User) -> list:
    return (
        db.query(Subscription)
        .filter(
            Subscription.user_id == user.id,
            Subscription.status.notin_(ENDED),
        )
        .all()
    )
