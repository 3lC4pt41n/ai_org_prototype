import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field, constr
from sqlalchemy.sql import func
from sqlmodel import select

from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Tenant

# Load JWT config from environment with defaults
SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(32)
    logging.warning("No SECRET_KEY provided in .env! Using an insecure default key.")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# Initialize password hashing context (using bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/api", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: constr(min_length=8)
    name: Optional[str] = Field(default=None, min_length=2, description="Display or project name")


def hash_password(p: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(p)


def get_password_hash(p: str) -> str:
    """Compatibility wrapper mirroring earlier naming."""
    return hash_password(p)


def verify_password(p: str, hashed: str) -> bool:
    """Verify a plaintext password against a hashed value."""
    try:
        return pwd_context.verify(p, hashed)
    except Exception:
        return False


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a JWT access token containing the provided payload."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/register")
def register(payload: RegisterIn):
    email = _normalize_email(payload.email)
    with SessionLocal() as session:
        existing = session.exec(
            select(Tenant).where(func.lower(Tenant.email) == email)
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
        tenant = Tenant(
            email=email,
            name=payload.name or email.split("@")[0],
            hashed_password=hash_password(payload.password),
        )
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        token = create_access_token(
            data={"sub": tenant.id, "tenant_id": tenant.id},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    email = _normalize_email(form_data.username)
    with SessionLocal() as session:
        tenant = session.exec(
            select(Tenant).where(func.lower(Tenant.email) == email)
        ).first()
        if not tenant or not tenant.hashed_password:
            raise HTTPException(status_code=400, detail="Incorrect email or password")
        if not verify_password(form_data.password, tenant.hashed_password):
            raise HTTPException(status_code=400, detail="Incorrect email or password")
        token = create_access_token(
            data={"sub": tenant.id, "tenant_id": tenant.id},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        )
    return {"access_token": token, "token_type": "bearer"}
