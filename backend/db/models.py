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
    
    # Progress tracking fields
    analysis_status = Column(String, default='pending')  # 'pending', 'processing', 'completed', 'failed'
    progress_percentage = Column(Integer, default=0)  # 0-100
    total_variants = Column(Integer, default=0)
    processed_variants = Column(Integer, default=0)
    current_step = Column(String, default='initializing')  # Current processing step
    estimated_completion = Column(DateTime(timezone=True))  # Estimated completion time
    
    # Relationship to user
    user = relationship("User", back_populates="genetic_analyses")
    
    # Relationship to variants
    variants = relationship("GeneticVariant", back_populates="analysis")

class GeneticVariant(Base):
    __tablename__ = "genetic_variants"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
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
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    condition = Column(String, nullable=False)
    risk_level = Column(String, nullable=False)  # 'low', 'moderate', 'high'
    risk_score = Column(String)
    associated_variants = Column(JSON)  # List of variant IDs
    recommendations = Column(JSON)  # List of recommendations
    
class DrugResponse(Base):
    __tablename__ = "drug_responses"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    gene = Column(String, nullable=False)
    drug = Column(String, nullable=False)
    response_type = Column(String)  # 'poor', 'intermediate', 'normal', 'rapid'
    recommendations = Column(Text)
    variants_involved = Column(JSON)

class PhysicalTrait(Base):
    __tablename__ = "physical_traits"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    trait_name = Column(String, nullable=False)
    trait_category = Column(String, nullable=False)  # 'appearance', 'athletic', 'sensory'
    genetic_result = Column(String, nullable=False)
    confidence = Column(String)  # 'high', 'moderate', 'low'
    associated_variants = Column(JSON)
    description = Column(Text)

class NutritionTrait(Base):
    __tablename__ = "nutrition_traits"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    nutrient = Column(String, nullable=False)
    metabolism_type = Column(String)  # 'normal', 'slow', 'fast', 'deficient'
    dietary_recommendations = Column(JSON)
    associated_variants = Column(JSON)
    sensitivity_level = Column(String)

class SportsPerformance(Base):
    __tablename__ = "sports_performance"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    performance_category = Column(String, nullable=False)  # 'endurance', 'power', 'recovery'
    genetic_advantage = Column(String)  # 'high', 'moderate', 'low'
    sport_recommendations = Column(JSON)
    associated_variants = Column(JSON)
    training_advice = Column(Text)

class CognitiveProfile(Base):
    __tablename__ = "cognitive_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    cognitive_domain = Column(String, nullable=False)  # 'memory', 'processing_speed', 'learning'
    genetic_score = Column(String)
    percentile = Column(Integer)
    associated_variants = Column(JSON)
    enhancement_suggestions = Column(JSON)

class PersonalityTrait(Base):
    __tablename__ = "personality_traits"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    trait_name = Column(String, nullable=False)  # 'openness', 'conscientiousness', etc.
    genetic_tendency = Column(String)
    confidence_level = Column(String)
    associated_variants = Column(JSON)
    behavioral_insights = Column(JSON)

class AncestryResult(Base):
    __tablename__ = "ancestry_results"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    population = Column(String, nullable=False)
    percentage = Column(String)
    confidence = Column(String)
    geographic_origin = Column(String)
    associated_variants = Column(JSON)

class CarrierStatus(Base):
    __tablename__ = "carrier_status"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    condition = Column(String, nullable=False)
    carrier_status = Column(String)  # 'carrier', 'non-carrier', 'affected'
    inheritance_pattern = Column(String)  # 'autosomal_recessive', 'x-linked', etc.
    associated_variants = Column(JSON)
    genetic_counseling_recommended = Column(Boolean, default=False)

class WellnessMetric(Base):
    __tablename__ = "wellness_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    metric_name = Column(String, nullable=False)  # 'sleep_quality', 'stress_response', etc.
    genetic_predisposition = Column(String)
    optimization_score = Column(String)
    lifestyle_recommendations = Column(JSON)
    associated_variants = Column(JSON)

class MethylationProfile(Base):
    __tablename__ = "methylation_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    gene = Column(String, nullable=False)  # 'MTHFR', 'COMT', 'MTR', etc.
    variant = Column(String)
    methylation_capacity = Column(String)  # 'normal', 'reduced', 'impaired'
    supplement_recommendations = Column(JSON)
    associated_variants = Column(JSON)

class DetoxificationProfile(Base):
    __tablename__ = "detoxification_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    detox_phase = Column(String, nullable=False)  # 'phase1', 'phase2', 'phase3'
    gene = Column(String, nullable=False)
    detox_capacity = Column(String)  # 'normal', 'slow', 'fast', 'impaired'
    toxin_sensitivity = Column(String)
    support_recommendations = Column(JSON)
    associated_variants = Column(JSON)