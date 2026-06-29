from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import models, schemas, auth, subscription_logic
from app.database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/register", response_model=schemas.AdminOut, status_code=status.HTTP_201_CREATED)
def register_admin(payload: schemas.AdminCreate, db: Session = Depends(get_db)):
    """
    NOTE: In production this endpoint must be locked down (e.g. invite-only,
    behind an internal network, or removed entirely in favor of a seed
    script) so the public can't self-register as AYX staff. Left open here
    only for MVP bootstrapping/demo purposes.
    """
    existing = db.query(models.Admin).filter(models.Admin.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Admin email already registered")

    admin = models.Admin(
        email=payload.email,
        hashed_password=auth.hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@router.post("/login", response_model=schemas.Token)
def admin_login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    admin = db.query(models.Admin).filter(models.Admin.email == form_data.username).first()
    if not admin or not auth.verify_password(form_data.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = auth.create_access_token(subject=admin.id, scope="admin")
    return schemas.Token(access_token=token)


@router.get("/orders", response_model=list[schemas.OrderOut])
def list_all_orders(
    status_filter: Optional[models.OrderStatus] = None,
    current_admin: models.Admin = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(models.Order)
    if status_filter:
        query = query.filter(models.Order.status == status_filter)
    return query.order_by(models.Order.created_at.desc()).all()


@router.patch("/orders/{order_id}/status", response_model=schemas.OrderOut)
def update_order_status(
    order_id: str,
    payload: schemas.OrderStatusUpdate,
    current_admin: models.Admin = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Admins manage order flow only -- per the spec, they do NOT manage
    payments/subscriptions. There is intentionally no admin endpoint that
    writes to the Subscription table.
    """
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = payload.status
    db.commit()
    db.refresh(order)
    return order


@router.get("/users/{user_id}/subscription", response_model=schemas.SubscriptionOut)
def view_user_subscription(
    user_id: str,
    current_admin: models.Admin = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    sub = subscription_logic.get_latest_subscription(db, user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="No subscription found for this user")
    return sub
