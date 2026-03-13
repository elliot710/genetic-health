"""
Database models for user authentication and genetic data storage
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON, Float, Index
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
    avatar_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
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
    
    # Relationship to variants (using optimized structure)
    analysis_variants = relationship("AnalysisVariant", back_populates="analysis", cascade="all, delete-orphan")


# Global marker catalog - stores every unique genetic marker ever uploaded.
# NEVER deleted when users remove their data. Enables deduplication and
# avoids redundant 3rd-party API calls for markers already in the system.
class GeneticMarker(Base):
    __tablename__ = "genetic_markers"
    
    id = Column(Integer, primary_key=True, index=True)
    rsid = Column(String, unique=True, nullable=False, index=True)
    chromosome = Column(String, nullable=False)
    position = Column(Integer, nullable=False)
    ref_allele = Column(String, nullable=False)
    alt_alleles = Column(String)  # Comma-separated list of all observed alt alleles
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    upload_count = Column(Integer, default=1)  # How many times this marker has been uploaded
    
    # Relationships
    analysis_variants = relationship("AnalysisVariant", back_populates="marker")
    shared_annotation = relationship("SharedVariantAnnotation", back_populates="marker", uselist=False)
    
    __table_args__ = (
        Index('ix_genetic_markers_chr_pos', 'chromosome', 'position'),
    )


class AnalysisVariant(Base):
    """Links a user's analysis to a global genetic marker with user-specific genotype data."""
    __tablename__ = "analysis_variants"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    marker_id = Column(Integer, ForeignKey("genetic_markers.id"), nullable=False)
    
    # User-specific data (genotype varies per person)
    genotype = Column(String)
    quality = Column(String)
    filter_status = Column(String)
    info = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    analysis = relationship("GeneticAnalysis", back_populates="analysis_variants")
    marker = relationship("GeneticMarker", back_populates="analysis_variants", lazy="joined")
    variant_annotations = relationship("VariantAnnotation", back_populates="analysis_variant", cascade="all, delete-orphan")
    
    # Proxy properties – delegate to the related GeneticMarker so that
    # existing code using variant.rsid / variant.chromosome etc. keeps working.
    @property
    def rsid(self):
        return self.marker.rsid if self.marker else None

    @property
    def chromosome(self):
        return self.marker.chromosome if self.marker else None

    @property
    def position(self):
        return self.marker.position if self.marker else None

    @property
    def ref_allele(self):
        return self.marker.ref_allele if self.marker else None

    @property
    def alt_allele(self):
        return self.marker.alt_alleles if self.marker else None

    __table_args__ = (
        Index('ix_analysis_variants_analysis_marker', 'analysis_id', 'marker_id'),
    )


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

# Shared variant annotations - never deleted when users delete their data.
# Linked to GeneticMarker for efficient lookup and API call deduplication.
class SharedVariantAnnotation(Base):
    __tablename__ = "shared_variant_annotations"
    
    id = Column(Integer, primary_key=True, index=True)
    marker_id = Column(Integer, ForeignKey("genetic_markers.id"), nullable=False, unique=True, index=True)
    rsid = Column(String, nullable=False, unique=True, index=True)  # Denormalized for fast lookup
    
    # Raw API responses stored as JSON for future analysis
    ensembl_data = Column(JSON)  # Complete Ensembl API response
    clinvar_data = Column(JSON)  # Complete ClinVar API response
    pharmgkb_data = Column(JSON)  # ClinPGx API response (column kept as pharmgkb_data for backward compat)
    snpedia_data = Column(JSON)  # Complete SNPedia API response
    litvar_data = Column(JSON)  # Complete LitVar/PubMed API response
    alpha_missense_data = Column(JSON)  # AlphaMissense AI pathogenicity prediction (local data, NOT clinically validated)
    
    # Metadata for tracking and reuse
    first_annotated_at = Column(DateTime(timezone=True), server_default=func.now())
    last_updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    annotation_status = Column(String, default='completed')  # 'pending', 'completed', 'failed', 'partial'
    total_api_calls = Column(Integer, default=0)  # Total API calls made for this variant
    failed_sources = Column(JSON, default=list)  # List of API sources that failed, e.g. ['ensembl', 'pharmgkb']
    usage_count = Column(Integer, default=0)  # How many times this annotation has been used
    
    # Relationships
    marker = relationship("GeneticMarker", back_populates="shared_annotation")
    
    __table_args__ = (
        Index('ix_shared_variant_annotations_marker_id', 'marker_id'),
    )


# User-specific variant annotation references - links user variants to shared annotations
class VariantAnnotation(Base):
    __tablename__ = "variant_annotations"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_variant_id = Column(Integer, ForeignKey("analysis_variants.id", ondelete="CASCADE"), nullable=False)
    shared_annotation_id = Column(Integer, ForeignKey("shared_variant_annotations.id"), nullable=True)  # Reference to shared annotation
    rsid = Column(String, nullable=False, index=True)
    
    # User-specific annotation data (if any customization is needed)
    user_notes = Column(Text)  # Optional user notes
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    analysis_variant = relationship("AnalysisVariant", back_populates="variant_annotations")
    analysis = relationship("GeneticAnalysis")
    shared_annotation = relationship("SharedVariantAnnotation")


class RareMutation(Base):
    __tablename__ = "rare_mutations"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    mutation_type = Column(String, nullable=False)  # 'pathogenic', 'likely_pathogenic', 'vus_high_impact'
    gene = Column(String, nullable=False)
    mutation_name = Column(String)  # Common name or clinical designation
    clinical_significance = Column(String)  # 'high', 'very_high', 'uncertain_high'
    disease_association = Column(String)  # Associated disease/condition
    penetrance = Column(String)  # 'high', 'moderate', 'low', 'variable'
    inheritance_pattern = Column(String)  # 'autosomal_dominant', 'autosomal_recessive', 'x_linked'
    population_frequency = Column(Float)  # Allele frequency in general population
    clinical_actions = Column(JSON)  # Recommended clinical actions
    specialist_referral = Column(Boolean, default=False)
    genetic_counseling_urgent = Column(Boolean, default=False)
    monitoring_recommendations = Column(JSON)
    family_screening_recommended = Column(Boolean, default=False)
    associated_variants = Column(JSON)
    
    # Relationship
    analysis = relationship("GeneticAnalysis")


class UncommonMutation(Base):
    __tablename__ = "uncommon_mutations"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False)
    mutation_type = Column(String, nullable=False)  # 'vus_moderate', 'benign_uncommon', 'protective_rare'
    gene = Column(String, nullable=False)
    mutation_name = Column(String)
    clinical_significance = Column(String)  # 'moderate', 'low', 'unclear', 'protective'
    trait_association = Column(String)  # Associated trait or condition
    effect_size = Column(String)  # 'small', 'moderate', 'large'
    population_frequency = Column(Float)  # Allele frequency (typically 0.1% - 5%)
    research_status = Column(String)  # 'well_studied', 'emerging', 'preliminary'
    lifestyle_implications = Column(JSON)  # Lifestyle recommendations
    monitoring_suggestions = Column(JSON)  # Optional monitoring
    research_participation = Column(String)  # 'recommended', 'optional', 'not_applicable'
    follow_up_timeline = Column(String)  # 'annual', 'biannual', 'as_needed'
    associated_variants = Column(JSON)
    
    # Relationship
    analysis = relationship("GeneticAnalysis")


class PanelMarkerConfig(Base):
    """Configures which genetic markers are used for each dashboard panel."""
    __tablename__ = "panel_marker_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    panel_id = Column(String, nullable=False, index=True)  # e.g. 'methylation', 'detox', 'health'
    rsid = Column(String, nullable=False)  # e.g. 'rs1801133'
    gene = Column(String)  # e.g. 'MTHFR'
    description = Column(String)  # Human-readable description
    category = Column(String)  # Sub-category within panel
    is_active = Column(Boolean, default=True)
    is_auto_discovered = Column(Boolean, default=False)  # True if created by auto-discovery
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        Index('ix_panel_marker_panel_rsid', 'panel_id', 'rsid', unique=True),
    )


class VariantMapping(Base):
    """Stores rsid→condition and gene→trait mappings used by the analysis engine.
    Replaces the static variant_registry.py file so mappings can be managed from the admin panel."""
    __tablename__ = "variant_mappings"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False, index=True)   # 'health', 'drug', 'physical', etc.
    map_type = Column(String, nullable=False)                # 'rsid' or 'gene'
    key = Column(String, nullable=False)                     # e.g. 'rs7903146' or 'TP73'
    data = Column(JSON, nullable=False)                      # Metadata dict (varies by category)
    is_active = Column(Boolean, default=True)
    is_auto_discovered = Column(Boolean, default=False)  # True if created by auto-discovery
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('ix_variant_mappings_cat_type_key', 'category', 'map_type', 'key', unique=True),
    )


class VariantLookupCache(Base):
    """Caches external variant lookup results to avoid redundant API calls."""
    __tablename__ = "variant_lookup_cache"

    id = Column(Integer, primary_key=True, index=True)
    variant_id = Column(String, unique=True, nullable=False, index=True)
    found = Column(Boolean, default=False)
    response_data = Column(JSON)        # Full processed response (basic_info, clinical_significance, etc.)
    raw_annotations = Column(JSON)      # Raw API annotations for re-processing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    lookup_count = Column(Integer, default=1)


class PendingDiscovery(Base):
    """Auto-discovered panel markers and variant mappings from user lookups.
    Requires admin approval before going live."""
    __tablename__ = "pending_discoveries"

    id = Column(Integer, primary_key=True, index=True)
    discovery_type = Column(String, nullable=False)  # 'panel_marker' or 'variant_mapping'
    rsid = Column(String, nullable=False, index=True)
    gene = Column(String)
    
    # For panel_marker discoveries
    panel_id = Column(String)  # e.g. 'health', 'drug_responses'
    description = Column(String)
    category = Column(String)  # Sub-category within panel
    
    # For variant_mapping discoveries
    map_type = Column(String)  # 'rsid' or 'gene'
    mapping_category = Column(String)  # e.g. 'health', 'drug'
    mapping_data = Column(JSON)  # The data dict for VariantMapping
    
    # Source data from the lookup that triggered the discovery
    source_data = Column(JSON)  # Snapshot of lookup data used to generate this
    
    # Status tracking
    status = Column(String, default='pending', nullable=False)  # 'pending', 'approved', 'rejected'
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(String, nullable=True)
    
    # Discovery metadata
    discovered_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # User who triggered the lookup
    lookup_count = Column(Integer, default=1)  # How many lookups produced the same suggestion
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('ix_pending_discoveries_type_rsid_panel', 'discovery_type', 'rsid', 'panel_id', unique=True),
        Index('ix_pending_discoveries_status', 'status'),
    )