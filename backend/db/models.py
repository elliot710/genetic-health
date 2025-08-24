"""
Database models for user authentication and genetic data storage
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship to genetic analyses
    genetic_analyses = relationship("GeneticAnalysis", back_populates="user")

class GeneticAnalysis(Base):
    __tablename__ = "genetic_analyses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # 'vcf' or 'csv'
    analysis_results = Column(JSON)  # Store the complete analysis results
    upload_date = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship to user
    user = relationship("User", back_populates="genetic_analyses")
    
    # Relationship to variants
    variants = relationship("GeneticVariant", back_populates="analysis")

class GeneticVariant(Base):
    __tablename__ = "genetic_variants"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id"), nullable=False)
    chromosome = Column(String, nullable=False)
    position = Column(Integer, nullable=False)
    rsid = Column(String, index=True)
    ref_allele = Column(String, nullable=False)
    alt_allele = Column(String, nullable=False)
    genotype = Column(String)
    quality = Column(String)
    filter_status = Column(String)
    info = Column(JSON)  # Additional variant information
    
    # Relationship to analysis
    analysis = relationship("GeneticAnalysis", back_populates="variants")

class HealthRisk(Base):
    __tablename__ = "health_risks"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id"), nullable=False)
    condition = Column(String, nullable=False)
    risk_level = Column(String, nullable=False)  # 'low', 'moderate', 'high'
    risk_score = Column(String)
    associated_variants = Column(JSON)  # List of variant IDs
    recommendations = Column(JSON)  # List of recommendations
    
class DrugResponse(Base):
    __tablename__ = "drug_responses"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id"), nullable=False)
    gene = Column(String, nullable=False)
    drug = Column(String, nullable=False)
    response_type = Column(String)  # 'poor', 'intermediate', 'normal', 'rapid'
    recommendations = Column(Text)
    variants_involved = Column(JSON)