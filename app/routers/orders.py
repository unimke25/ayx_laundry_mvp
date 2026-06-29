from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas, auth, subscription_logic
from app.database import get_db

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/", response_model=schemas.OrderOut, status_code=201)
def create_order(
    payload: schemas.OrderCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    # Hard constraint from spec: only active subscribers may book, no exceptions.
    allowed, reason = subscription_logic.can_book(db, current_user.id)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)

    sub = subscription_logic.get_latest_subscription(db, current_user.id)

    order = models.Order(
        user_id=current_user.id,
        pickup_address=payload.pickup_address,
        pickup_time=payload.pickup_time,
        delivery_time=payload.delivery_time,
        notes=payload.notes,
        subscription_status_at_booking=sub.status.value,
        plan_at_booking=sub.plan.value,
        status=models.OrderStatus.PENDING,
    )
    db.add(order)

    # Decrement pickup allowance (no-op for Unlimited, enforced via limit lookup)
    if models.PLAN_PICKUP_LIMITS.get(sub.plan) is not None:
        sub.pickups_used_this_period += 1

    db.commit()
    db.refresh(order)
    return order


@router.get("/my", response_model=list[schemas.OrderOut])
def list_my_orders(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Order)
        .filter(models.Order.user_id == current_user.id)
        .order_by(models.Order.created_at.desc())
        .all()
    )


@router.get("/{order_id}", response_model=schemas.OrderOut)
def get_order(
    order_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order or order.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
