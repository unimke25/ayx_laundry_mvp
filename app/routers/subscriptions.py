from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas, auth, subscription_logic
from app.database import get_db

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

BILLING_PERIOD_DAYS = 30


@router.post("/subscribe", response_model=schemas.SubscriptionOut)
def subscribe(
    payload: schemas.SubscribeRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates (or upgrades) a subscription. Real payment is NOT processed here
    -- per the spec, actual activation happens when the simulated
    checkout.session.completed Stripe event is received. This endpoint
    creates a PENDING-style record; for the MVP we immediately mark it
    ACTIVE for convenience, mirroring what the webhook would otherwise do.
    In a production flow, this endpoint would instead create a Stripe
    Checkout Session and return its URL, and activation would happen only
    via the webhook.
    """
    now = datetime.utcnow()
    sub = models.Subscription(
        user_id=current_user.id,
        plan=payload.plan,
        status=models.SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=now + timedelta(days=BILLING_PERIOD_DAYS),
        pickups_used_this_period=0,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.get("/status", response_model=schemas.SubscriptionOut)
def subscription_status(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    sub = subscription_logic.get_latest_subscription(db, current_user.id)
    if not sub:
        raise HTTPException(status_code=404, detail="No subscription found")
    return sub


@router.post("/cancel", response_model=schemas.SubscriptionOut)
def cancel_subscription(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Marks the subscription to cancel at period end (no immediate refund logic in MVP)."""
    sub = subscription_logic.get_latest_subscription(db, current_user.id)
    if not sub:
        raise HTTPException(status_code=404, detail="No subscription found")
    sub.cancel_at_period_end = True
    db.commit()
    db.refresh(sub)
    return sub
