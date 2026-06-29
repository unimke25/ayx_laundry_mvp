from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import models, schemas, auth
from app.database import get_db
from app.models import PlanType, PLAN_PICKUP_LIMITS

router = APIRouter(prefix="/auth", tags=["users"])


@router.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        email=payload.email,
        hashed_password=auth.hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm uses "username" field name; we treat it as email.
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = auth.create_access_token(subject=user.id, scope="user")
    return schemas.Token(access_token=token)


@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.get("/plans")
def list_plans():
    """Public endpoint: anyone can view available subscription plans."""
    return [
        {
            "plan": plan.value,
            "pickups_per_period": PLAN_PICKUP_LIMITS[plan],
            "description": _plan_description(plan),
        }
        for plan in PlanType
    ]


def _plan_description(plan: PlanType) -> str:
    return {
        PlanType.BASIC: "Limited pickups per month, standard turnaround.",
        PlanType.PREMIUM: "More pickups per month, faster turnaround.",
        PlanType.UNLIMITED: "No pickup limits, priority turnaround.",
    }[plan]
