import os
import hashlib
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from ai_org_backend.db import engine
from ai_org_backend.models import Tenant
import jwt

SECRET_KEY = os.getenv("JWT_SECRET", "secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

router = APIRouter(prefix="/api", tags=["auth"])


def hash_password(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()


def verify_password(p: str, hashed: str) -> bool:
    return hash_password(p) == hashed


def create_access_token(tenant_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"tenant_id": tenant_id, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/register")
def register(payload: dict):
    email = payload.get("email")
    password = payload.get("password")
    name = payload.get("name") or (email.split("@")[0] if email else None)
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")
    with Session(engine) as session:
        existing = session.exec(select(Tenant).where(Tenant.email == email)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        tenant = Tenant(email=email, name=name, hashed_password=hash_password(password))
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
    return {"id": tenant.id, "email": tenant.email}


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    with Session(engine) as session:
        tenant = session.exec(select(Tenant).where(Tenant.email == form_data.username)).first()
        if not tenant or not verify_password(form_data.password, tenant.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(tenant.id)
    return {"access_token": token, "token_type": "bearer"}
