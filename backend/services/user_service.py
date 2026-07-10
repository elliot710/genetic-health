"""
User service for database operations
"""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional, List
from ..db.models import (
    User, GeneticAnalysis,
    HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait,
    SportsPerformance, CognitiveProfile, PersonalityTrait,
    AncestryResult, CarrierStatus, WellnessMetric,
    MethylationProfile, DetoxificationProfile, RareMutation,
    UncommonMutation,
)
from ..db.schemas import UserCreate, UserUpdate
from ..core.auth import get_password_hash, verify_password

# Per-analysis insight tables included in a user's data export (mirrors
# INSIGHT_TABLES in insight_dispatcher.py — duplicated per this codebase's
# convention rather than cross-imported).
_INSIGHT_MODELS = (
    HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait,
    SportsPerformance, CognitiveProfile, PersonalityTrait,
    AncestryResult, CarrierStatus, WellnessMetric,
    MethylationProfile, DetoxificationProfile, RareMutation,
    UncommonMutation,
)

# Explicit allowlist — never export hashed_password or other auth internals.
_PROFILE_EXPORT_FIELDS = (
    "id", "email", "username", "full_name", "avatar_url",
    "auth_provider", "is_verified", "created_at",
)


def _to_json_safe(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _row_to_dict(row) -> dict:
    return {c.name: _to_json_safe(getattr(row, c.name)) for c in row.__table__.columns}


def _profile_to_dict(user: User) -> dict:
    return {field: _to_json_safe(getattr(user, field)) for field in _PROFILE_EXPORT_FIELDS}


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user"""
        hashed_password = get_password_hash(user_data.password)
        
        db_user = User(
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            hashed_password=hashed_password
        )
        
        self.db.add(db_user)
        await self.db.commit()
        await self.db.refresh(db_user)
        return db_user
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username/email and password"""
        # Try to get user by username first, then by email
        user = await self.get_user_by_username(username)
        if not user:
            user = await self.get_user_by_email(username)
        
        if not user or not verify_password(password, str(user.hashed_password)):
            return None
        
        return user
    
    async def update_user(self, user_id: int, user_update: UserUpdate) -> Optional[User]:
        """Update user information"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        
        update_data = user_update.model_dump(exclude_unset=True)
        
        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        
        for field, value in update_data.items():
            setattr(user, field, value)
        
        await self.db.commit()
        await self.db.refresh(user)
        return user
    
    async def update_password(self, user_id: int, new_password: str) -> None:
        """Update a user's password."""
        user = await self.get_user_by_id(user_id)
        if user:
            user.hashed_password = get_password_hash(new_password)
            await self.db.commit()

    async def get_or_create_google_user(
        self, email: str, google_id: str, full_name: str, avatar_url: str | None
    ) -> "User":
        """Find an existing user by Google ID or email, or create one."""
        from ..db.models import User as UserModel
        # 1. Look up by google_id
        result = await self.db.execute(
            select(UserModel).where(UserModel.google_id == google_id)
        )
        user = result.scalar_one_or_none()
        if user:
            return user

        # 2. Look up by email (link existing account)
        user = await self.get_user_by_email(email)
        if user:
            user.google_id = google_id
            user.auth_provider = "google"
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            await self.db.commit()
            await self.db.refresh(user)
            return user

        # 3. Create new user
        import re
        base = re.sub(r"[^a-z0-9]", "", email.split("@")[0].lower()) or "user"
        username = base
        suffix = 1
        while await self.get_user_by_username(username):
            username = f"{base}{suffix}"
            suffix += 1

        db_user = UserModel(
            email=email,
            username=username,
            full_name=full_name,
            avatar_url=avatar_url,
            google_id=google_id,
            auth_provider="google",
            hashed_password=None,
            is_verified=True,
        )
        self.db.add(db_user)
        await self.db.commit()
        await self.db.refresh(db_user)
        return db_user

    async def get_user_analyses(self, user_id: int) -> List[GeneticAnalysis]:
        """Get all genetic analyses for a user"""
        result = await self.db.execute(
            select(GeneticAnalysis)
            .where(
                GeneticAnalysis.user_id == user_id,
                GeneticAnalysis.deleted_at.is_(None),
            )
            .options(selectinload(GeneticAnalysis.variants))
            .order_by(GeneticAnalysis.upload_date.desc())
        )
        return list(result.scalars().all())

    async def delete_account(self, user: User) -> None:
        """Hard-delete a user and all their personal data.

        Relies on the ORM cascade declared on User.genetic_analyses (see
        models.py), which cascades through genetic_analyses to the 14
        insight tables and variant rows. Never touches shared caches
        (genetic_markers, shared_variant_annotations, gnomad/clinvar).
        """
        await self.db.delete(user)
        await self.db.commit()

    async def export_account_data(self, user: User) -> dict:
        """Return the user's profile, analyses, and insight rows as JSON.

        Scoped strictly to this user: every analysis query filters by
        GeneticAnalysis.user_id and every insight query filters by
        analysis_id, so shared reference caches (genetic_markers,
        shared_variant_annotations, gnomad/clinvar source tables) are never
        read or included.
        """
        result = await self.db.execute(
            select(GeneticAnalysis).where(GeneticAnalysis.user_id == user.id)
        )
        analyses = result.scalars().all()
        return {
            "profile": _profile_to_dict(user),
            "analyses": [await self._export_analysis(a) for a in analyses],
        }

    async def _export_analysis(self, analysis: GeneticAnalysis) -> dict:
        exported = {
            "id": analysis.id,
            "filename": analysis.filename,
            "file_type": analysis.file_type,
            "analysis_status": analysis.analysis_status,
            "upload_date": _to_json_safe(analysis.upload_date),
            "inferred_sex": analysis.inferred_sex,
        }
        for model in _INSIGHT_MODELS:
            result = await self.db.execute(
                select(model).where(model.analysis_id == analysis.id)
            )
            exported[model.__tablename__] = [_row_to_dict(row) for row in result.scalars().all()]
        return exported
