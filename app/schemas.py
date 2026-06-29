"""
Pydantic schemas (request/response contracts). Kept separate from the ORM
models so the API surface can evolve independently of the DB schema, and so
sensitive fields (password hashes) are never accidentally serialized.
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field

from app.models import PlanType, SubscriptionStatus, OrderStatus


# ---------- Auth / Users ----------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Admin ----------

class AdminCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str


class AdminLogin(BaseModel):
    email: EmailStr
    password: str


class AdminOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str

    class Config:
        from_attributes = True


# ---------- Subscriptions ----------

class SubscribeRequest(BaseModel):
    plan: PlanType


class SubscriptionOut(BaseModel):
    id: str
    plan: PlanType
    status: SubscriptionStatus
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    pickups_used_this_period: int

    class Config:
        from_attributes = True


# ---------- Orders ----------

class OrderCreate(BaseModel):
    pickup_address: str
    pickup_time: datetime
    delivery_time: Optional[datetime] = None
    notes: Optional[str] = None


class OrderOut(BaseModel):
    id: str
    user_id: str
    pickup_address: str
    pickup_time: datetime
    delivery_time: Optional[datetime]
    notes: Optional[str]
    subscription_status_at_booking: str
    plan_at_booking: str
    status: OrderStatus
    created_at: datetime

    class Config:
        from_attributes = True


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


# ---------- Simulated Stripe ----------

class SimulateStripeEvent(BaseModel):
    event_type: str = Field(
        description=(
            "One of: checkout.session.completed, invoice.payment_succeeded, "
            "customer.subscription.updated, customer.subscription.deleted"
        )
    )
    user_id: str
    plan: Optional[PlanType] = None
