"""
Centralized subscription business logic.

Per the spec's hard constraint -- "Only active subscribers may book orders,
no exceptions" -- this check is implemented ONCE here and imported wherever
booking eligibility matters, rather than re-implemented per-route. This
avoids the classic bug where one endpoint enforces the rule and another
forgets to.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app import models


def get_latest_subscription(db: Session, user_id: str) -> Optional[models.Subscription]:
    return (
        db.query(models.Subscription)
        .filter(models.Subscription.user_id == user_id)
        .order_by(models.Subscription.created_at.desc())
        .first()
    )


def is_subscription_active(sub: Optional[models.Subscription]) -> bool:
    """
    A subscription is considered active if:
    - it exists,
    - its status is ACTIVE, and
    - the current period end has not passed (defends against stale status
      in case a renewal/expiry webhook hasn't been simulated/received yet).
    """
    if sub is None:
        return False
    if sub.status != models.SubscriptionStatus.ACTIVE:
        return False
    if sub.current_period_end and sub.current_period_end < datetime.utcnow():
        return False
    return True


def pickup_allowance_remaining(sub: models.Subscription) -> Optional[int]:
    """Returns remaining pickups this period, or None if unlimited."""
    limit = models.PLAN_PICKUP_LIMITS.get(sub.plan)
    if limit is None:
        return None
    return max(limit - sub.pickups_used_this_period, 0)


def can_book(db: Session, user_id: str) -> tuple[bool, str]:
    """
    Returns (allowed, reason). Reason is human-readable, used for the
    booking endpoint's error response.
    """
    sub = get_latest_subscription(db, user_id)
    if not is_subscription_active(sub):
        return False, "No active subscription. Subscribe or renew to book a pickup."

    remaining = pickup_allowance_remaining(sub)
    if remaining is not None and remaining <= 0:
        return False, (
            f"You've used all pickups included in your {sub.plan.value} plan "
            f"for this billing period. Upgrade your plan or wait for renewal."
        )
    return True, ""
