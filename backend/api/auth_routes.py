"""
Authentication API routes
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sa_delete
from datetime import timedelta
from pydantic import BaseModel
from typing import Optional, List

from ..db.database import get_session
from ..db.schemas import UserCreate, UserResponse, Token, UserLogin
from ..db.models import User, SavedVariant
from ..services.user_service import UserService
from ..core.auth import (
    create_access_token, create_refresh_token, verify_token, verify_refresh_token,
    verify_password, get_password_hash, ACCESS_TOKEN_EXPIRE_MINUTES,
    set_auth_cookies, clear_auth_cookies, ACCESS_COOKIE,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer(auto_error=False)  # auto_error=False so cookie fallback works

@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_session)):
    """Register a new user"""
    user_service = UserService(db)
    
    # Check if user already exists
    existing_user = await user_service.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    existing_username = await user_service.get_user_by_username(user_data.username)
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create new user
    user = await user_service.create_user(user_data)
    return UserResponse.model_validate(user)

@router.post("/login")
async def login(user_data: UserLogin, response: Response, db: AsyncSession = Depends(get_session)):
    """Login user — sets HttpOnly auth cookies and returns token for API-client compat."""
    user_service = UserService(db)
    
    user = await user_service.authenticate_user(user_data.username, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": user.username})

    # Set HttpOnly cookies
    set_auth_cookies(response, access_token, refresh_token)
    
    # Still return token in body for backwards compat (Swagger UI, mobile clients, etc.)
    return Token(access_token=access_token, token_type="bearer")

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_session)
) -> User:
    """Get current authenticated user from HttpOnly cookie or Bearer header."""
    token: Optional[str] = None

    # 1. Try HttpOnly cookie first
    token = request.cookies.get(ACCESS_COOKIE)

    # 2. Fall back to Bearer header (Swagger UI, API clients)
    if not token and credentials:
        token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = verify_token(token)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_service = UserService(db)
    user = await user_service.get_user_by_username(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

@router.get("/me", response_model=UserResponse)
async def get_me(current_user = Depends(get_current_user)):
    """Get current user profile"""
    return UserResponse.model_validate(current_user)


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


@router.put("/me", response_model=UserResponse)
async def update_profile(
    update: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Update current user profile"""
    if update.full_name is not None:
        current_user.full_name = update.full_name
    if update.avatar_url is not None:
        # Validate avatar_url is a reasonable data URI or empty string to clear
        if update.avatar_url == "":
            current_user.avatar_url = None
        elif update.avatar_url.startswith("data:image/") and len(update.avatar_url) <= 500_000:
            current_user.avatar_url = update.avatar_url
        else:
            raise HTTPException(status_code=400, detail="Invalid avatar data")
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Change current user password"""
    if not verify_password(data.current_password, str(current_user.hashed_password)):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    current_user.hashed_password = get_password_hash(data.new_password)
    await db.commit()
    return {"detail": "Password changed successfully"}


@router.post("/logout")
async def logout(response: Response):
    """Clear auth cookies to log the user out."""
    clear_auth_cookies(response)
    return {"detail": "Logged out"}


@router.post("/refresh")
async def refresh_access_token(request: Request, response: Response, db: AsyncSession = Depends(get_session)):
    """Issue a fresh access-token cookie using the refresh-token cookie."""
    refresh_tok = request.cookies.get("refresh_token")
    if not refresh_tok:
        raise HTTPException(status_code=401, detail="No refresh token")

    username = verify_refresh_token(refresh_tok)
    if not username:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Verify the user still exists
    user_service = UserService(db)
    user = await user_service.get_user_by_username(username)
    if not user:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="User not found")

    # Issue new tokens
    access_token = create_access_token(data={"sub": username})
    new_refresh = create_refresh_token(data={"sub": username})
    set_auth_cookies(response, access_token, new_refresh)
    return {"detail": "Token refreshed"}


# ── Saved Variants ───────────────────────────────────────────────

class SaveVariantRequest(BaseModel):
    rsid: str
    gene: Optional[str] = None
    most_severe_consequence: Optional[str] = None
    clinical_significance: Optional[str] = None
    note: Optional[str] = None


class SavedVariantResponse(BaseModel):
    id: int
    rsid: str
    gene: Optional[str] = None
    most_severe_consequence: Optional[str] = None
    clinical_significance: Optional[str] = None
    note: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


@router.get("/saved-variants", response_model=List[SavedVariantResponse])
async def list_saved_variants(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all saved variants for the current user."""
    result = await db.execute(
        select(SavedVariant)
        .where(SavedVariant.user_id == current_user.id)
        .order_by(SavedVariant.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        SavedVariantResponse(
            id=r.id,
            rsid=r.rsid,
            gene=r.gene,
            most_severe_consequence=r.most_severe_consequence,
            clinical_significance=r.clinical_significance,
            note=r.note,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]


@router.post("/saved-variants", response_model=SavedVariantResponse, status_code=201)
async def save_variant(
    body: SaveVariantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Save a variant to the user's bookmarks."""
    # Check for duplicate
    existing = await db.execute(
        select(SavedVariant).where(
            SavedVariant.user_id == current_user.id,
            SavedVariant.rsid == body.rsid,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Variant already saved")

    sv = SavedVariant(
        user_id=current_user.id,
        rsid=body.rsid,
        gene=body.gene,
        most_severe_consequence=body.most_severe_consequence,
        clinical_significance=body.clinical_significance,
        note=body.note,
    )
    db.add(sv)
    await db.commit()
    await db.refresh(sv)
    return SavedVariantResponse(
        id=sv.id,
        rsid=sv.rsid,
        gene=sv.gene,
        most_severe_consequence=sv.most_severe_consequence,
        clinical_significance=sv.clinical_significance,
        note=sv.note,
        created_at=sv.created_at.isoformat() if sv.created_at else "",
    )


@router.delete("/saved-variants/{rsid}")
async def unsave_variant(
    rsid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Remove a variant from the user's bookmarks."""
    result = await db.execute(
        sa_delete(SavedVariant).where(
            SavedVariant.user_id == current_user.id,
            SavedVariant.rsid == rsid,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Variant not found in saved list")
    await db.commit()
    return {"detail": "Variant removed"}