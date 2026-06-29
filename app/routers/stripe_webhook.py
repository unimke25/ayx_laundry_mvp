"""
Simulated Stripe webhook handling.

In a real integration, Stripe would POST signed events to a webhook
endpoint, and we'd verify the signature with stripe.Webhook.construct_event
using a webhook secret. Since the spec requires hooks to be SIMULATED (not
real) for the MVP, this router exposes a single endpoint that lets you
trigger any of the four required event types manually (e.g. from a test
script, an admin tool, or curl) and applies the same state transitions a
real webhook handler would.

When wiring up real Stripe later, the only change needed is: replace the
SimulateStripeEvent body with the verified Stripe Event object, and keep
the event_type dispatch logic below as-is.
"""

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas, subscription_logic
from app.database import get_db

router = APIRouter(prefix="/stripe", tags=["stripe-simulated"])

BILLING_PERIOD_DAYS = 30

SUPPORTED_EVENTS = {
    "checkout.session.completed",
    "invoice.payment_succeeded",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}


@router.post("/simulate-event")
def simulate_stripe_event(payload: schemas.SimulateStripeEvent, db: Session = Depends(get_db)):
    if payload.event_type not in SUPPORTED_EVENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported event_type. Must be one of: {sorted(SUPPORTED_EVENTS)}",
        )

    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    log = models.StripeEventLog(
        event_type=payload.event_type,
        user_id=user.id,
        payload=json.dumps(payload.model_dump(mode="json")),
    )
    db.add(log)

    sub = subscription_logic.get_latest_subscription(db, user.id)
    now = datetime.utcnow()

    if payload.event_type == "checkout.session.completed":
        # New subscription purchase completes -> activate.
        if not sub:
            if not payload.plan:
                raise HTTPException(
                    status_code=400, detail="plan is required to create a subscription"
                )
            sub = models.Subscription(user_id=user.id, plan=payload.plan)
            db.add(sub)
        sub.status = models.SubscriptionStatus.ACTIVE
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=BILLING_PERIOD_DAYS)
        sub.pickups_used_this_period = 0
        sub.cancel_at_period_end = False

    elif payload.event_type == "invoice.payment_succeeded":
        # Renewal payment succeeded -> extend period, reset usage.
        if not sub:
            raise HTTPException(status_code=404, detail="No subscription to renew")
        sub.status = models.SubscriptionStatus.ACTIVE
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=BILLING_PERIOD_DAYS)
        sub.pickups_used_this_period = 0

    elif payload.event_type == "customer.subscription.updated":
        # Plan change, or payment failed -> reflect new plan/status.
        if not sub:
            raise HTTPException(status_code=404, detail="No subscription to update")
        if payload.plan:
            sub.plan = payload.plan

    elif payload.event_type == "customer.subscription.deleted":
        # Subscription cancelled/ended -> mark cancelled, lose booking access.
        if not sub:
            raise HTTPException(status_code=404, detail="No subscription to cancel")
        sub.status = models.SubscriptionStatus.CANCELLED
        sub.cancel_at_period_end = True

    log.processed = True
    db.commit()
    db.refresh(sub) if sub else None

    return {
        "received": True,
        "event_type": payload.event_type,
        "subscription_status": sub.status.value if sub else None,
    }
