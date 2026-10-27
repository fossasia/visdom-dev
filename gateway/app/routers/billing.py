"""
Billing router: subscription plans, the current user's subscription with real
usage against plan limits, Stripe checkout and the Stripe customer portal, and
the webhook Stripe reports subscription changes to.
"""

from typing import List

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app import bypass, payments
from app.billing import DEFAULT_TIER, get_plan, ordered_plans, selectable
from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models import Plan, User
from app.schemas import (
    CheckoutStarted,
    CheckoutStatus,
    PlanResponse,
    PortalLink,
    SubscriptionResponse,
    SubscriptionUpdate,
)
from app.usage import MEGABYTE, allowances, storage_used, usage

router = APIRouter(prefix="/billing", tags=["billing"])


def _build_subscription(db: Session, user: User) -> dict:
    tier = user.tier or DEFAULT_TIER
    plan = get_plan(db, tier)
    limits = allowances(db, user)

    counts = usage(db, user)
    workspaces_used = counts["workspaces"]
    members_used = counts["members"]
    api_keys_used = counts["api_keys"]

    return {
        "tier": tier,
        "plan": _offer(plan),
        "support_contact": settings.SUPPORT_CONTACT.strip() or None,
        "limits_bypassed": bypass.applies_to(db, user),
        "billing": _billing_state(db, user),
        "usage": {
            "workspaces": {"used": workspaces_used, "limit": limits["workspaces"]},
            "members": {"used": members_used, "limit": limits["members"]},
            "api_keys": {"used": api_keys_used, "limit": limits["api_keys"]},
            "storage": {
                "used": storage_used(db, user),
                "limit": None if limits.get("storage_mb") is None else limits["storage_mb"] * MEGABYTE,
            },
        },
    }


def _offer(plan: dict) -> dict:
    return {**plan, "checkout": payments.buyable(plan)}


def _billing_state(db: Session, user: User) -> dict:
    live = payments.current(db, user)
    return {
        "enabled": payments.enabled(),
        "status": live.status if live else None,
        "plan_id": live.plan_id if live else None,
        "renews_at": None if live is None or live.ends_at else live.current_period_end,
        "ends_at": live.ends_at if live else None,
        "can_manage": payments.enabled() and bool(user.stripe_customer_id) and payments.has_subscribed(db, user),
    }


def _require_payments() -> None:
    if not payments.enabled():
        raise HTTPException(status_code=503, detail="Payments are not set up yet.")


def _unreachable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/plans", response_model=List[PlanResponse])
def list_plans(db: Session = Depends(get_db)):
    """Returns the plans an account can see and pick."""
    return [_offer(plan) for plan in ordered_plans(db)]


@router.get("/subscription", response_model=SubscriptionResponse)
def get_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the current user's plan and real usage against its limits."""
    return _build_subscription(db, current_user)


@router.post("/subscription", response_model=SubscriptionResponse)
def update_subscription(
    payload: SubscriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Moves the current user onto a free plan.

    Only a public, current plan that costs nothing can be picked here. A paid
    plan is bought through checkout, and leaving one is done from the Stripe
    customer portal, so that what an account is held to always matches what it
    pays for. Staff can still put an account on any plan from the admin console.
    """
    if not selectable(db, payload.tier):
        raise HTTPException(
            status_code=422,
            detail="That plan is not available.",
        )
    plan = get_plan(db, payload.tier)
    if plan["price"] is None:
        raise HTTPException(
            status_code=422,
            detail="That plan is arranged with the Visdom team. Get in touch to set it up.",
        )
    if plan["price"] > 0:
        raise HTTPException(
            status_code=402,
            detail="Paid plans are bought through checkout."
            if payments.buyable(plan)
            else "That plan cannot be bought online yet.",
        )
    if payments.current(db, current_user) is not None:
        raise HTTPException(
            status_code=409,
            detail="You have a paid plan. Cancel it from Manage billing to move to a free plan.",
        )
    current_user.tier = payload.tier
    db.commit()
    db.refresh(current_user)
    return _build_subscription(db, current_user)


@router.post("/checkout", response_model=CheckoutStarted)
def start_checkout(
    payload: SubscriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_payments()
    plan = db.get(Plan, payload.tier)
    if plan is None or not selectable(db, payload.tier) or not payments.buyable(get_plan(db, payload.tier)):
        raise HTTPException(status_code=422, detail="That plan cannot be bought online.")
    if payments.current(db, current_user) is not None:
        raise HTTPException(
            status_code=409,
            detail="You already have a paid plan. Change it from Manage billing.",
        )
    try:
        started = payments.start_checkout(db, current_user, plan)
    except payments.AlreadyPaying as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except payments.PaymentsDown as exc:
        raise _unreachable(exc) from exc
    return {**started, "publishable_key": settings.STRIPE_PUBLISHABLE_KEY}


@router.get("/checkout/{session_id}", response_model=CheckoutStatus)
def checkout_status(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_payments()
    try:
        session = payments.checkout_for(current_user, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="No such checkout.")
        if session.get("status") == "complete" and session.get("subscription"):
            subscription = session["subscription"]
            if isinstance(subscription, dict):
                subscription = subscription.get("id")
            payments.sync(db, subscription)
    except payments.PaymentsDown as exc:
        raise _unreachable(exc) from exc
    db.refresh(current_user)
    return {"status": session.get("status"), "subscription": _build_subscription(db, current_user)}


@router.post("/renewal", response_model=SubscriptionResponse)
def resume_renewal(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_payments()
    try:
        resumed = payments.resume_renewing(db, current_user)
    except payments.PaymentsDown as exc:
        raise _unreachable(exc) from exc
    if resumed is None:
        raise HTTPException(status_code=409, detail="There is no paid plan set to end.")
    db.refresh(current_user)
    return _build_subscription(db, current_user)


@router.post("/portal", response_model=PortalLink)
def open_portal(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_payments()
    if not current_user.stripe_customer_id or not payments.has_subscribed(db, current_user):
        raise HTTPException(status_code=409, detail="There is nothing to manage yet.")
    try:
        return {"url": payments.portal_url(current_user)}
    except payments.PaymentsDown as exc:
        raise _unreachable(exc) from exc


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    try:
        event = payments.read_event(payload, request.headers.get("stripe-signature"))
    except payments.PaymentsOff as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook signature.") from exc
    try:
        await run_in_threadpool(payments.handle, db, event)
    except (payments.PaymentsOff, payments.PaymentsDown) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"received": True}
