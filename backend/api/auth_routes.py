"""
Authentication API routes
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sa_delete
from datetime import timedelta, datetime, timezone
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import asyncio
import smtplib
import secrets
import urllib.parse
import json
import base64
import os
import logging
import requests as http_requests

from ..db.database import get_session
from ..db.schemas import UserCreate, UserResponse, Token, UserLogin
from ..db.models import User, SavedVariant
from ..services.user_service import UserService
from ..core.config import settings
from ..core.rate_limit import limiter
from ..core.auth import (
    create_access_token, create_refresh_token, verify_token, verify_refresh_token,
    verify_password, get_password_hash, ACCESS_TOKEN_EXPIRE_MINUTES,
    set_auth_cookies, clear_auth_cookies, ACCESS_COOKIE,
    SECRET_KEY, ALGORITHM,
)
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer(auto_error=False)  # auto_error=False so cookie fallback works

# ─── Google OAuth config ───────────────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "https://api.epigenic.xyz/auth/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://epigenic.xyz")

# ─── Password reset helpers ───────────────────────────────────────────────────
RESET_TOKEN_EXPIRE_MINUTES = 60

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

def create_reset_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": email, "type": "password_reset", "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def verify_reset_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "password_reset":
            return None
        return payload.get("sub")
    except JWTError:
        return None

async def _send_reset_email(email: str, reset_url: str) -> None:
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user:
        logger.warning(f"SMTP not configured. Password reset URL for {email}: {reset_url}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your Epigenic.xyz password"
    msg["From"] = smtp_from
    msg["To"] = email

    html = f"""
    <html><body style="font-family:sans-serif;background:#f0fdf4;padding:32px;">
      <div style="max-width:480px;margin:auto;background:white;border-radius:12px;padding:32px;box-shadow:0 4px 24px rgba(0,0,0,.08);">
        <h2 style="color:#0d9488;margin-bottom:8px;">Reset your password</h2>
        <p style="color:#374151;">Click the button below to reset your Epigenic.xyz password. This link expires in 1 hour.</p>
        <a href="{reset_url}" style="display:inline-block;margin:24px 0;padding:12px 28px;background:#0d9488;color:white;text-decoration:none;border-radius:8px;font-weight:600;">Reset Password</a>
        <p style="color:#9ca3af;font-size:12px;">If you didn't request this, you can safely ignore this email.</p>
      </div>
    </body></html>
    """
    msg.attach(MIMEText(html, "html"))

    def _send():
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, email, msg.as_string())

    await asyncio.to_thread(_send)


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
@limiter.limit(lambda: f"{settings.rate_limit.auth_per_minute}/minute")
async def login(request: Request, user_data: UserLogin, response: Response, db: AsyncSession = Depends(get_session)):
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
    if not current_user.hashed_password:
        raise HTTPException(status_code=400, detail="Password login is not enabled for this account")
    if not verify_password(data.current_password, str(current_user.hashed_password)):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    current_user.hashed_password = get_password_hash(data.new_password)
    await db.commit()
    return {"detail": "Password changed successfully"}


@router.delete("/account")
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Permanently delete the current user's account and all personal data."""
    service = UserService(db)
    await service.delete_account(current_user)
    return {"detail": "Account and all associated data deleted"}


@router.get("/account/export")
async def export_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Export the current user's profile, analyses, and insight data as JSON."""
    service = UserService(db)
    return await service.export_account_data(current_user)


@router.post("/logout")
async def logout(response: Response):
    """Clear auth cookies to log the user out."""
    clear_auth_cookies(response)
    return {"detail": "Logged out"}


DEFAULT_NOTIFICATION_PREFERENCES: dict[str, bool] = {
    "analysis_queued": True,
    "analysis_completed": True,
    "analysis_failed": True,
    "upload_complete": True,
    "upload_failed": True,
    "variant_saved": True,
    "discovery_approved": True,
    "discovery_rejected": True,
    "data_deleted": True,
    "dashboard_shared": True,
}


@router.get("/ws-token")
async def get_ws_token(request: Request, current_user: User = Depends(get_current_user)):
    """Return the raw access token from the HttpOnly cookie for WebSocket use.

    WebSocket connections in browsers cannot use HttpOnly cookies directly via
    the WS query-param pattern, so this endpoint bridges the gap.
    """
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="No access token cookie found")
    return {"token": token}


@router.get("/notification-preferences")
async def get_notification_preferences(current_user: User = Depends(get_current_user)):
    """Return the user's notification preferences (all default to True)."""
    prefs = dict(DEFAULT_NOTIFICATION_PREFERENCES)
    if current_user.notification_preferences:
        prefs.update(current_user.notification_preferences)
    return prefs


class NotificationPreferencesUpdate(BaseModel):
    preferences: dict[str, bool]


@router.put("/notification-preferences")
async def update_notification_preferences(
    body: NotificationPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Update notification preferences. Only known keys accepted."""
    unknown = set(body.preferences) - set(DEFAULT_NOTIFICATION_PREFERENCES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown preference keys: {sorted(unknown)}")
    existing: dict = dict(current_user.notification_preferences or {})
    existing.update(body.preferences)
    current_user.notification_preferences = existing
    await db.commit()
    # Return full merged prefs
    merged = dict(DEFAULT_NOTIFICATION_PREFERENCES)
    merged.update(existing)
    return merged


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
    genotype: Optional[str] = None
    most_severe_consequence: Optional[str] = None
    clinical_significance: Optional[str] = None
    note: Optional[str] = None


class SavedVariantResponse(BaseModel):
    id: int
    rsid: str
    gene: Optional[str] = None
    genotype: Optional[str] = None
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
            genotype=r.genotype,
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
        genotype=body.genotype,
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
        genotype=sv.genotype,
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


class UpdateSavedVariantRequest(BaseModel):
    note: Optional[str] = None


@router.patch("/saved-variants/{rsid}", response_model=SavedVariantResponse)
async def update_saved_variant(
    rsid: str,
    body: UpdateSavedVariantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Update the note on a saved variant."""
    result = await db.execute(
        select(SavedVariant).where(
            SavedVariant.user_id == current_user.id,
            SavedVariant.rsid == rsid,
        )
    )
    sv = result.scalar_one_or_none()
    if not sv:
        raise HTTPException(status_code=404, detail="Variant not found in saved list")
    sv.note = body.note
    await db.commit()
    await db.refresh(sv)
    return SavedVariantResponse(
        id=sv.id,
        rsid=sv.rsid,
        gene=sv.gene,
        genotype=sv.genotype,
        most_severe_consequence=sv.most_severe_consequence,
        clinical_significance=sv.clinical_significance,
        note=sv.note,
        created_at=sv.created_at.isoformat() if sv.created_at else "",
    )


# ─── Forgot / Reset Password ──────────────────────────────────────────────────

@router.post("/forgot-password", status_code=202)
@limiter.limit(lambda: f"{settings.rate_limit.auth_per_minute}/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest, db: AsyncSession = Depends(get_session)):
    """Send a password reset email. Always returns 202 to avoid email enumeration."""
    user_service = UserService(db)
    user = await user_service.get_user_by_email(str(data.email))
    if user:
        token = create_reset_token(str(data.email))
        reset_url = f"{FRONTEND_URL}?mode=reset&token={token}"
        try:
            await _send_reset_email(str(data.email), reset_url)
        except Exception as exc:
            logger.error(f"Failed to send reset email to {data.email}: {exc}")
    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
@limiter.limit(lambda: f"{settings.rate_limit.auth_per_minute}/minute")
async def reset_password(request: Request, data: ResetPasswordRequest, db: AsyncSession = Depends(get_session)):
    """Reset password using a valid reset token."""
    email = verify_reset_token(data.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    user_service = UserService(db)
    user = await user_service.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    await user_service.update_password(user.id, data.new_password)
    return {"message": "Password reset successfully"}


# ─── Google OAuth ─────────────────────────────────────────────────────────────

@router.get("/google")
async def google_login():
    """Redirect the browser to Google's OAuth2 consent screen."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return RedirectResponse(url)


@router.get("/google/callback")
@limiter.limit(lambda: f"{settings.rate_limit.auth_per_minute}/minute")
async def google_callback(
    request: Request,
    code: str,
    response: Response,
    db: AsyncSession = Depends(get_session),
    error: Optional[str] = None,
):
    """Handle Google OAuth2 callback: exchange code, find/create user, set cookies."""
    if error or not code:
        return RedirectResponse(f"{FRONTEND_URL}?error=oauth_cancelled")

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return RedirectResponse(f"{FRONTEND_URL}?error=oauth_not_configured")

    # Exchange authorization code for tokens
    try:
        token_resp = await asyncio.to_thread(
            http_requests.post,
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_json = token_resp.json()
    except Exception as exc:
        logger.error(f"Google token exchange failed: {exc}")
        return RedirectResponse(f"{FRONTEND_URL}?error=oauth_failed")

    if "error" in token_json:
        logger.error(f"Google token error: {token_json}")
        return RedirectResponse(f"{FRONTEND_URL}?error=oauth_failed")

    # Decode the ID token (JWT) — verify with Google's public keys via google-auth
    id_token_str = token_json.get("id_token")
    if not id_token_str:
        return RedirectResponse(f"{FRONTEND_URL}?error=no_id_token")

    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        user_info = await asyncio.to_thread(
            google_id_token.verify_oauth2_token,
            id_token_str,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        logger.error(f"Google ID token verification failed: {exc}")
        return RedirectResponse(f"{FRONTEND_URL}?error=token_invalid")

    email = user_info.get("email")
    google_id = user_info.get("sub")
    if not email or not google_id:
        return RedirectResponse(f"{FRONTEND_URL}?error=no_email")

    user_service = UserService(db)
    user = await user_service.get_or_create_google_user(
        email=email,
        google_id=google_id,
        full_name=user_info.get("name", ""),
        avatar_url=user_info.get("picture"),
    )

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    redirect = RedirectResponse(url=FRONTEND_URL)
    set_auth_cookies(redirect, access_token, refresh_token)
    return redirect
