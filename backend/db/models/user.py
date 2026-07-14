"""User authentication, sharing and saved-variant models.

Split out of the former db/models.py module; see the package __init__.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON, Float, Index, BigInteger, SmallInteger, ARRAY, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.db.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    full_name = Column(String)
    avatar_url = Column(String, nullable=True)
    google_id = Column(String, unique=True, nullable=True, index=True)
    auth_provider = Column(String(20), default="local", nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship to genetic analyses
    # passive_deletes: rely on the DB's ON DELETE CASCADE chain (users -> genetic_analyses
    # -> variants/annotations/insight tables, all FKs ondelete=CASCADE) instead of loading
    # the whole per-genome object graph (600k+ variant rows) into the event loop on account
    # deletion. Emits a single DELETE FROM users; Postgres cascades the rest.
    genetic_analyses = relationship("GeneticAnalysis", back_populates="user",
                                    cascade="all, delete-orphan", passive_deletes=True)
    saved_variants = relationship("SavedVariant", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    # Notification preferences — JSON map of type → bool, e.g. {"analysis_completed": true}
    notification_preferences = Column(JSON, nullable=True)
    # Shares I created (as owner)
    shares_given = relationship("DashboardShare", foreign_keys="DashboardShare.owner_id", back_populates="owner", cascade="all, delete-orphan")
    # Shares others created for me (as recipient)
    shares_received = relationship("DashboardShare", foreign_keys="DashboardShare.recipient_id", back_populates="recipient", cascade="all, delete-orphan")


class Notification(Base):
    """In-app notifications for user events (analysis completion, uploads, etc.)."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(64), nullable=False)  # e.g. 'analysis_completed', 'upload_complete'
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    data = Column(JSON, nullable=True)          # extra payload (analysis_id, filename, …)
    read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_user_id_created", "user_id", "created_at"),
    )


class DashboardShare(Base):
    """Records that owner has granted recipient access to view their dashboard."""
    __tablename__ = "dashboard_shares"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", foreign_keys=[owner_id], back_populates="shares_given")
    recipient = relationship("User", foreign_keys=[recipient_id], back_populates="shares_received")

    __table_args__ = (
        UniqueConstraint("owner_id", "recipient_id", name="uq_dashboard_share"),
        Index("ix_dashboard_shares_owner", "owner_id"),
        Index("ix_dashboard_shares_recipient", "recipient_id"),
    )


class SavedVariant(Base):
    """User-bookmarked variants for quick access from the profile."""
    __tablename__ = "saved_variants"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rsid = Column(String, nullable=False)
    gene = Column(String, nullable=True)
    genotype = Column(String, nullable=True)
    most_severe_consequence = Column(String, nullable=True)
    clinical_significance = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="saved_variants")

    __table_args__ = (
        UniqueConstraint("user_id", "rsid", name="uq_saved_variant_user_rsid"),
        Index("ix_saved_variants_user_id", "user_id"),
    )
