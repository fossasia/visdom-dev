"""
Billing router: subscription plans, the current user's subscription with real
usage against plan limits, and downgrades from paid tiers.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException,status
from sqlalchemy.orm import Session

from app.billing import DEFAULT_TIER, get_plan, ordered_plans, selectable
from app.dependencies import get_current_user, get_db, lock_user_for_workspace_quota
from app.models import APIKey, Membership, User, Workspace
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
    """Allows downgrades; paid tiers require a verified subscription entitlement."""
    user = lock_user_for_workspace_quota(db, current_user.id)
    if user is None:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    if not user.is_active:
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    if payload.tier != DEFAULT_TIER and payload.tier != user.tier:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Paid plan changes require a verified subscription.",
        )

    user.tier = payload.tier
    db.commit()
    db.refresh(user)
    return _build_subscription(db, user)
