from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token
from app.schemas.auth import UserLogin, UserCreate, UserOut, Token

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    # Simple demonstration user auth or db lookup
    if credentials.email == "admin@privacyshield.ai" and credentials.password == "admin123":
        token = create_access_token(subject=credentials.email)
        return {"access_token": token, "token_type": "bearer"}
    
    token = create_access_token(subject=credentials.email)
    return {"access_token": token, "token_type": "bearer"}

@router.post("/register", response_model=UserOut)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    return UserOut(
        id="user-demo-123",
        email=user_in.email,
        full_name=user_in.full_name,
        role=user_in.role or "analyst",
        is_active=True
    )
