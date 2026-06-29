"""
SQLAlchemy models for the AYX Laundry MVP.

Schema decisions (explained per the spec's requirement to justify SQLite
design choices):

- Users / Admins are separate tables rather than a single table with a
  "role" flag. This keeps the admin surface area small and lets us apply
  stricter constraints/auth flows to admins without touching user logic.
  For an MVP with a handful of staff accounts, a separate table is simpler
  to reason about than role-based access control on one table.

- Subscriptions is its own table (not columns on User) because a user's
  subscription has its own lifecycle (status, renewal date, Stripe IDs)
  that changes independently of profile data, and because it lets us keep
  a history if we later allow plan changes/re-subscriptions. One-to-one
  for the MVP, but modeled as one-to-many-ready (subscription has a
  user_id FK) so multiple historical subscriptions per user are possible
  later without a schema change.

- Orders store a *snapshot* of subscription status at booking time
  (subscription_status_at_booking) in addition to the live FK to the
  user. This is intentional: if a subscription later expires or is
  cancelled, we still want an accurate record of what the user's
  status was when they placed that order (audit trail / dispute
  resolution).

- StripeEventLog stores raw simulated webhook events for traceability,
  mirroring how a real Stripe integration would log events for
  idempotency and debugging.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class PlanType(str, enum.Enum):
    BASIC = "BASIC"
    PREMIUM = "PREMIUM"
    UNLIMITED = "UNLIMITED"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    PAST_DUE = "PAST_DUE"  # failed payment, grace period
    NONE = "NONE"  # never subscribed


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    PICKED_UP = "PICKED_UP"
    IN_PROGRESS = "IN_PROGRESS"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


# Pickup allowances per plan, used to enforce "limited number of pickups"
# for Basic/Premium. Unlimited has no cap (None = unlimited).
PLAN_PICKUP_LIMITS = {
    PlanType.BASIC: 4,       # pickups per billing cycle
    PlanType.PREMIUM: 10,
    PlanType.UNLIMITED: None,
}


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    subscriptions = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")


class Admin(Base):
    __tablename__ = "admins"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    plan = Column(SAEnum(PlanType), nullable=False)
    status = Column(SAEnum(SubscriptionStatus), default=SubscriptionStatus.NONE)

    # Simulated Stripe linkage fields
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)

    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)

    pickups_used_this_period = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    pickup_address = Column(String, nullable=False)
    pickup_time = Column(DateTime, nullable=False)
    delivery_time = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    # Snapshot of subscription status at the moment of booking (audit trail)
    subscription_status_at_booking = Column(String, nullable=False)
    plan_at_booking = Column(String, nullable=False)

    status = Column(SAEnum(OrderStatus), default=OrderStatus.PENDING)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="orders")


class StripeEventLog(Base):
    """
    Stores simulated Stripe webhook events for traceability/idempotency,
    mirroring how a production integration would log raw event payloads.
    """

    __tablename__ = "stripe_event_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    event_type = Column(String, nullable=False)
    stripe_event_id = Column(String, unique=True, nullable=False, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    payload = Column(Text, nullable=True)  # JSON string of simulated payload
    received_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)
