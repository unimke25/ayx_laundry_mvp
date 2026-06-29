"""
Authentication utilities: password hashing (bcrypt via passlib) and JWT
issuance/verification (python-jose).

Security notes:
- Passwords are never stored in plaintext; bcrypt hashing is one-way and
  salted automatically by passlib.
- JWTs carry the subject (user id) and a "scope" claim ("user" or "admin")
  so the same token mechanism can't be replayed across the two auth
  domains -- a user token will not pass admin checks, and vice versa.
- SECRET_KEY MUST be overridden via environment variable in any real
  deployment. The default here is only for local MVP development and is
  intentionally obvious so nobody mistakes it for production-ready.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

# Loads variables from a local .env file (if present) into os.environ.
# In production, set real environment variables instead of relying on .env.
load_dotenv()

# --- Config (override via environment variables in real deployments) ---
SECRET_KEY = os.environ.get("AYX_SECRET_KEY", "dev-only-CHANGE-ME-before-deploy")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24h, fine for MVP

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_user_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
oauth2_admin_scheme = OAuth2PasswordBearer(tokenUrl="/admin/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, scope: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "scope": scope, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )


def get_current_user(
    token: str = Depends(oauth2_user_scheme), db: Session = Depends(get_db)
) -> models.User:
    payload = _decode_token(token)
    if payload.get("scope") != "user":
        raise HTTPException(status_code=403, detail="Not a user token")
    user = db.query(models.User).filter(models.User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def get_current_admin(
    token: str = Depends(oauth2_admin_scheme), db: Session = Depends(get_db)
) -> models.Admin:
    payload = _decode_token(token)
    if payload.get("scope") != "admin":
        raise HTTPException(status_code=403, detail="Not an admin token")
    admin = db.query(models.Admin).filter(models.Admin.id == payload["sub"]).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found")
    return admin
