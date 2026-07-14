"""Dashboard trait/profile result tables.

Split out of the former db/models.py module; see the package __init__.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON, Float, Index, BigInteger, SmallInteger, ARRAY, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.db.database import Base


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
    # Structured ancestry data (JSON blobs consumed by the frontend)
    composition = Column(JSON)           # [{region, percentage}, ...]
    maternal_haplogroup = Column(JSON)   # {haplogroup, origin, frequency, age, description}
    paternal_haplogroup = Column(JSON)   # {haplogroup, origin, frequency, age, description}
    neanderthal_variants = Column(JSON)  # {percentage, variants, moreOrLess, comparison}

class CarrierStatus(Base):
    __tablename__ = "carrier_status"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    condition = Column(String, nullable=False)
    carrier_status = Column(String)  # 'carrier', 'non-carrier', 'affected'
    inheritance_pattern = Column(String)  # 'autosomal_recessive', 'x-linked', etc.
    associated_variants = Column(JSON)
    genetic_counseling_recommended = Column(Boolean, default=False)
    gene = Column(String, nullable=True)

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

# Shared variant annotations - never deleted when users delete their data.
# Linked to GeneticMarker for efficient lookup and API call deduplication.
