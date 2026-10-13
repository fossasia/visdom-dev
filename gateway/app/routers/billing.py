"""
Billing router: subscription plans, the current user's subscription with real
usage against plan limits, and (payment-free) plan changes.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.billing import DEFAULT_TIER, get_plan, ordered_plans, selectable
from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import PlanResponse, SubscriptionResponse, SubscriptionUpdate
from app.usage import usage

router = APIRouter(prefix="/billing", tags=["billing"])


def _build_subscription(db: Session, user: User) -> dict:
    tier = user.tier or DEFAULT_TIER
    plan = get_plan(db, tier)
    limits = plan["limits"]

    counts = usage(db, user)
    workspaces_used = counts["workspaces"]
    members_used = counts["members"]
    api_keys_used = counts["api_keys"]

    return {
        "tier": tier,
        "plan": plan,
        "usage": {
            "workspaces": {"used": workspaces_used, "limit": limits["workspaces"]},
            "members": {"used": members_used, "limit": limits["members"]},
            "api_keys": {"used": api_keys_used, "limit": limits["api_keys"]},
        },
    }


@router.get("/plans", response_model=List[PlanResponse])
def list_plans(db: Session = Depends(get_db)):
    """Returns the plans an account can see and pick."""
    return ordered_plans(db)


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
    """Changes the current user's plan. No payment processing yet.

    Only a public, current plan can be picked here. An account cannot move
    itself onto a hidden or archived plan, since changing plan costs nothing yet.
    """
    if not selectable(db, payload.tier):
        raise HTTPException(
            status_code=422,
            detail="That plan is not available.",
        )
    current_user.tier = payload.tier
    db.commit()
    db.refresh(current_user)
    return _build_subscription(db, current_user)
