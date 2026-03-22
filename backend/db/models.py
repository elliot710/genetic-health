"""
Database models for user authentication and genetic data storage
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON, Float, Index, BigInteger, SmallInteger, ARRAY, UniqueConstraint
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
    saved_variants = relationship("SavedVariant", back_populates="user", cascade="all, delete-orphan")


class SavedVariant(Base):
    """User-bookmarked variants for quick access from the profile."""
    __tablename__ = "saved_variants"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rsid = Column(String, nullable=False)
    gene = Column(String, nullable=True)
    most_severe_consequence = Column(String, nullable=True)
    clinical_significance = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="saved_variants")

    __table_args__ = (
        UniqueConstraint("user_id", "rsid", name="uq_saved_variant_user_rsid"),
        Index("ix_saved_variants_user_id", "user_id"),
    )


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
    
    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Persisted job logs (JSON array of {ts, level, msg} entries)
    job_logs = Column(JSON, nullable=True)
    
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
    gene_symbol = Column(String(50))  # Cached gene symbol (PERF-04) — filled after first analysis

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
    analysis_id = Column(Integer, ForeignKey("genetic_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
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
    gene = Column(String(100))  # Gene symbol (FE-01)
    review_status = Column(String(200))  # ClinVar review status for evidence level (FE-02/03)
    pathogenicity_classification = Column(String(30))  # benign, likely_benign, uncertain, likely_pathogenic, pathogenic
    
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
    clinvar_local_data = Column(JSON)  # ClinVar local TSV data (variant_summary + citations + cross-refs + gene stats)
    gnomad_data = Column(JSON)  # gnomAD population frequencies + constraint metrics (local/BigQuery)
    gnomad_tx_data = Column(JSON)  # gnomAD tx_annotated: gene/consequence/LoF/GTEx tissue expression (tabix)
    thousand_genomes_data = Column(JSON)  # 1000 Genomes Phase 3 population frequencies (local ETL)
    chembl_data = Column(JSON)  # ChEMBL drug mechanisms, indications, warnings (BigQuery)
    fda_drug_data = Column(JSON)  # FDA drug label CYP interactions (BigQuery)
    alphafold_data = Column(JSON)  # AlphaFold protein structure confidence (BigQuery)
    
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

    __table_args__ = (
        UniqueConstraint('analysis_id', 'analysis_variant_id', name='uq_variant_annotations_analysis_variant'),
    )


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
    sources = Column(JSON, nullable=True)     # e.g. ["clinvar_local", "ensembl_vep", "gnomad"]
    confidence = Column(Float, nullable=True)  # 0.0–1.0 based on source agreement
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


class AnnotationSourceConfig(Base):
    """Admin-configurable annotation sources. Controls which external APIs are
    called during variant annotation, with the ability to enable/disable and
    backfill later from newly-enabled sources."""
    __tablename__ = "annotation_source_configs"

    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String, unique=True, nullable=False, index=True)  # 'ensembl', 'clinvar', 'clinpgx', 'snpedia'
    display_name = Column(String, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    description = Column(String)
    # source_type: 'api' = third-party HTTP API, 'database' = PostgreSQL-backed,
    # 'file' = local tabix/TSV files in data_sources/ only,
    # 'hybrid' = both local files in data_sources/ AND PostgreSQL import,
    # 'bigquery' = Google BigQuery
    source_type = Column(String, default='api')  # 'api' | 'database' | 'file' | 'hybrid' | 'bigquery'
    rate_limit = Column(Float)  # req/s — informational for the admin UI
    priority = Column(Integer, default=0)  # Lower = higher priority
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


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


# ==============================================================================
# ClinVar local data tables — imported from TSV + VCF files via ETL.
# Replaces in-memory loading for fast indexed lookups and zero startup cost.
# ==============================================================================

class ClinVarVariant(Base):
    """Core ClinVar variant record — one row per (rsid, allele_id) pair.
    Denormalized for fast single-query lookups. This is the primary ClinVar
    lookup table used during analysis."""
    __tablename__ = "clinvar_variants"

    id = Column(BigInteger, primary_key=True)
    rsid = Column(String, nullable=False)                            # e.g. 'rs7903146'
    allele_id = Column(String)                                       # ClinVar AlleleID
    variation_id = Column(String)                                    # ClinVar VariationID

    # Clinical
    clinical_significance = Column(String)                           # e.g. 'Pathogenic', 'Likely_pathogenic'
    review_status = Column(String)                                   # ClinVar review stars text
    conditions = Column(String)                                      # Semicolon-separated condition names
    origin = Column(String)                                          # 'germline', 'somatic', etc.
    variation_type = Column(String)                                  # 'single nucleotide variant', etc.

    # Genomic location
    gene = Column(String)                                             # Gene symbol
    gene_id = Column(String)                                         # NCBI Gene ID
    chromosome = Column(String)                                      # '1' .. '22', 'X', 'Y', 'MT'
    start_pos = Column(Integer)
    stop_pos = Column(Integer)
    assembly = Column(String)                                        # 'GRCh37' or 'GRCh38'

    # Accessions
    rcv_accession = Column(String)                                   # RCV accession(s)
    phenotype_ids = Column(String)                                   # MedGen/OMIM/Orphanet IDs

    # HGVS nomenclature
    hgvs_nucleotide = Column(String)
    hgvs_protein = Column(String)

    # VCF-derived fields (allele frequencies, molecular consequences, oncology)
    molecular_consequence = Column(String)                           # e.g. 'missense_variant'
    af_exac = Column(Float)                                          # ExAC allele frequency
    af_tgp = Column(Float)                                           # 1000 Genomes allele frequency
    af_esp = Column(Float)                                           # GO-ESP allele frequency
    oncogenicity = Column(String)                                    # ClinVar oncogenicity
    somatic_clinical_impact = Column(String)                         # Somatic clinical impact
    conflicting_classifications = Column(Text)                       # Conflicting interpretation text

    # Metadata
    data_source = Column(String, default='tsv')                     # 'tsv', 'vcf', or 'merged'
    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_clinvar_variants_rsid', 'rsid'),
        Index('ix_clinvar_variants_gene', 'gene'),
        Index('ix_clinvar_variants_significance', 'clinical_significance'),
        Index('ix_clinvar_variants_rsid_allele', 'rsid', 'allele_id'),
    )


class ClinVarGeneCondition(Base):
    """Gene → disease associations from ClinVar's gene_condition_source_id.txt.
    Used for gene-based category inference and enrichment."""
    __tablename__ = "clinvar_gene_conditions"

    id = Column(Integer, primary_key=True)
    gene = Column(String, nullable=False)                            # Indexed in __table_args__
    disease_name = Column(String, nullable=False)
    source_name = Column(String)                                     # 'OMIM', 'MedGen', etc.
    source_id = Column(String)                                       # External source ID
    disease_mim = Column(String)                                     # OMIM disease number
    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_clinvar_gene_conditions_gene', 'gene'),
    )


class ClinVarGeneStats(Base):
    """Per-gene ClinVar statistics from gene_specific_summary.txt.
    Provides aggregate submission counts and pathogenicity overview."""
    __tablename__ = "clinvar_gene_stats"

    id = Column(Integer, primary_key=True, index=True)
    gene = Column(String, nullable=False, unique=True, index=True)
    gene_id = Column(String)
    total_submissions = Column(Integer, default=0)
    total_alleles = Column(Integer, default=0)
    pathogenic_likely_pathogenic = Column(Integer, default=0)
    uncertain_significance = Column(Integer, default=0)
    with_conflicts = Column(Integer, default=0)
    gene_mim = Column(String)
    imported_at = Column(DateTime(timezone=True), server_default=func.now())


# ==============================================================================
# Category rules engine — auto-maps ClinVar/AlphaMissense annotations to
# dashboard categories. Admin-configurable; replaces manual variant_mappings
# curation for bulk expansion.
# ==============================================================================

class CategoryRule(Base):
    """Configurable rules for auto-assigning variants to dashboard categories.
    Evaluated in priority order (lower number = higher priority).

    Rule types:
      - clinvar_significance: match clinical_significance (e.g. 'Pathogenic')
      - clinvar_condition_keyword: match condition text (e.g. 'cancer')
      - gene_list: match gene symbol (comma-separated list in rule_value)
      - molecular_consequence: match consequence type (e.g. 'missense_variant')
      - am_class: match AlphaMissense classification (e.g. 'pathogenic')
      - am_score_above / am_score_below: AlphaMissense pathogenicity score threshold
      - origin: match ClinVar origin (e.g. 'germline', 'somatic')
    """
    __tablename__ = "category_rules"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False, index=True)            # Target category: 'health', 'drug', etc.
    rule_type = Column(String, nullable=False)                       # Type of rule (see docstring)
    rule_value = Column(Text, nullable=False)                        # The value/pattern to match
    priority = Column(Integer, default=50)                           # Lower = higher priority
    is_active = Column(Boolean, default=True)

    # Optional enrichment data — attached to generated VariantMapping
    mapping_data_template = Column(JSON)                             # Template for VariantMapping.data

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('ix_category_rules_cat_type', 'category', 'rule_type'),
    )


# ==============================================================================
# gnomAD local data tables — imported from TSV files via ETL or queried from
# BigQuery on demand. Stores population allele frequencies, constraint metrics,
# and variant annotations for the Genome Aggregation Database.
# ==============================================================================

class GnomadVariant(Base):
    """Core gnomAD variant record — one row per unique variant.
    Stores CADD pathogenicity scores, functional predictions, conservation,
    and (from BigQuery) population allele frequencies.
    Primary lookup table used during analysis for variant annotation."""
    __tablename__ = "gnomad_variants"

    id = Column(BigInteger, primary_key=True)
    chrom = Column(String, nullable=False)                           # '1'..'22', 'X', 'Y'
    pos = Column(Integer, nullable=False)                            # Genomic position
    ref = Column(String, nullable=False)                             # Reference allele
    alt = Column(String, nullable=False)                             # Alternate allele
    rsid = Column(String)                                            # dbSNP rsid (may be null)
    variant_id = Column(String)                                      # chrom-pos-ref-alt canonical ID
    variant_type = Column(String)                                    # INS, DEL, SNV

    # Quality
    filter_status = Column(String)                                   # 'PASS', 'AC0', 'InbreedingCoeff', etc.

    # Global allele frequency (populated from BigQuery, not in CADD TSV)
    af = Column(Float)                                               # Global allele frequency
    ac = Column(Integer)                                             # Global allele count
    an = Column(Integer)                                             # Global allele number
    nhomalt = Column(Integer)                                        # Number of homozygous alt individuals

    # Population-specific allele frequencies (populated from BigQuery)
    af_afr = Column(Float)                                           # African/African-American
    af_ami = Column(Float)                                           # Amish
    af_amr = Column(Float)                                           # Latino/Admixed American
    af_asj = Column(Float)                                           # Ashkenazi Jewish
    af_eas = Column(Float)                                           # East Asian
    af_fin = Column(Float)                                           # Finnish
    af_mid = Column(Float)                                           # Middle Eastern
    af_nfe = Column(Float)                                           # Non-Finnish European
    af_sas = Column(Float)                                           # South Asian
    af_remaining = Column(Float)                                     # Remaining populations

    # CADD scores (from local CADD-annotated TSV)
    cadd_raw = Column(Float)                                         # CADD raw score
    cadd_phred = Column(Float)                                       # CADD PHRED-scaled (>20 = top 1% deleterious)

    # Functional predictions
    sift_cat = Column(String)                                        # SIFT: tolerated, deleterious, etc.
    sift_val = Column(Float)                                         # SIFT numeric score
    polyphen_cat = Column(String)                                    # PolyPhen: benign, possibly_damaging, etc.
    polyphen_val = Column(Float)                                     # PolyPhen numeric score

    # Conservation scores
    phylop_primate = Column(Float)                                   # Primate PhyloP
    phylop_mammal = Column(Float)                                    # Mammalian PhyloP
    phylop_vertebrate = Column(Float)                                # Vertebrate PhyloP

    # SpliceAI scores
    splice_ai_acc_gain = Column(Float)                               # Acceptor gain
    splice_ai_acc_loss = Column(Float)                               # Acceptor loss
    splice_ai_don_gain = Column(Float)                               # Donor gain
    splice_ai_don_loss = Column(Float)                               # Donor loss

    # VEP annotations (structured)
    gene = Column(String)                                             # Gene symbol (from VEP)
    consequence = Column(String)                                     # Most severe consequence
    impact = Column(String)                                          # HIGH, MODERATE, LOW, MODIFIER
    hgvsc = Column(String)                                           # HGVS coding notation
    hgvsp = Column(String)                                           # HGVS protein notation

    # Full annotation blob (for forward compatibility)
    annotations = Column(JSON)                                       # All additional annotations as JSON

    # Source tracking
    data_source = Column(String, default='tsv')                     # 'tsv', 'bigquery'
    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_gnomad_variants_rsid', 'rsid'),
        Index('ix_gnomad_variants_chrom_pos', 'chrom', 'pos'),
        Index('ix_gnomad_variants_chrom_pos_ref_alt', 'chrom', 'pos', 'ref', 'alt', unique=True),
        Index('ix_gnomad_variants_gene', 'gene'),
        Index('ix_gnomad_variants_variant_id', 'variant_id'),
        Index('ix_gnomad_variants_cadd_phred', 'cadd_phred'),
    )


class GnomadGeneConstraint(Base):
    """Gene-level constraint metrics from gnomAD.
    pLI and LOEUF scores indicate how tolerant a gene is to loss-of-function mutations."""
    __tablename__ = "gnomad_gene_constraints"

    id = Column(Integer, primary_key=True)
    gene = Column(String, nullable=False, unique=True)               # Gene symbol
    transcript = Column(String)                                      # Canonical transcript ID

    # Constraint scores
    pli = Column(Float)                                              # Prob. of being loss-of-function intolerant
    loeuf = Column(Float)                                            # Loss-of-function observed/expected upper fraction
    mis_z = Column(Float)                                            # Missense Z-score
    syn_z = Column(Float)                                            # Synonymous Z-score

    # Counts
    obs_lof = Column(Integer)                                        # Observed loss-of-function variants
    exp_lof = Column(Float)                                          # Expected loss-of-function variants
    obs_mis = Column(Integer)                                        # Observed missense variants
    exp_mis = Column(Float)                                          # Expected missense variants
    obs_syn = Column(Integer)                                        # Observed synonymous variants
    exp_syn = Column(Float)                                          # Expected synonymous variants

    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_gnomad_gene_constraints_gene', 'gene'),
    )


class EnsemblGene(Base):
    """Local Ensembl gene model derived from cDNA/ncRNA FASTA headers.
    Used for position-based variant→gene mapping without hitting the Ensembl API."""
    __tablename__ = "ensembl_genes"

    id = Column(Integer, primary_key=True)
    gene_id = Column(String, nullable=False, unique=True)            # ENSG00000211751.9
    gene_symbol = Column(String, nullable=False, index=True)         # TRBC1
    chromosome = Column(String, nullable=False)                      # 7
    start_pos = Column(BigInteger, nullable=False)                   # Gene start (min of all transcripts)
    end_pos = Column(BigInteger, nullable=False)                     # Gene end (max of all transcripts)
    strand = Column(SmallInteger)                                    # 1 or -1
    biotype = Column(String)                                         # protein_coding, lncRNA, etc.
    description = Column(Text)                                       # Human-readable description
    transcript_count = Column(Integer, default=0)                    # Number of known transcripts

    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_ensembl_genes_chr_range', 'chromosome', 'start_pos', 'end_pos'),
    )


class EnsemblVepVariant(Base):
    """Local Ensembl VEP variant data parsed from Ensembl VCF dumps.
    Stores pre-formatted VEP consequences in the same schema as the REST API."""
    __tablename__ = "ensembl_vep_variants"

    id = Column(BigInteger, primary_key=True)
    rsid = Column(String, nullable=False, unique=True, index=True)
    chromosome = Column(String(5), nullable=False)
    position = Column(Integer, nullable=False)
    ref_allele = Column(String(500), nullable=False)
    alt_alleles = Column(String(1000), nullable=False)               # comma-separated ALTs
    variant_type = Column(String(20))                                # SNV, indel, etc.
    minor_allele = Column(String(50))
    minor_allele_freq = Column(Float)
    ancestral_allele = Column(String(500))
    clinical_significance = Column(ARRAY(String))                    # ['benign', 'pathogenic', ...]
    evidence = Column(ARRAY(String))                                 # ['Freq', '1000G', ...]
    most_severe_consequence = Column(String(100))                    # missense_variant, etc.
    impact = Column(String(20))                                      # HIGH, MODERATE, LOW, MODIFIER
    gene_symbol = Column(String(50))                                 # Best gene from consequence
    # Pre-formatted VEP data (matches Ensembl REST API response structure)
    vep_data = Column(JSON)                                          # Full API-compatible dict

    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_ensembl_vep_chr_pos', 'chromosome', 'position'),
    )


# ==============================================================================
# 1000 Genomes Phase 3 — imported from Ensembl VCF dump via ETL.
# Population allele frequencies for AFR, AMR, EAS, EUR, SAS superpopulations.
# ==============================================================================

class ThousandGenomesVariant(Base):
    """1000 Genomes Phase 3 variant record — one row per (chrom, pos, ref, alt).
    Stores population-level allele frequencies from the 1000 Genomes Project.
    Primary lookup table for ancestry-relevant population frequency data."""
    __tablename__ = "thousand_genomes_variants"

    id = Column(BigInteger, primary_key=True)
    chrom = Column(String, nullable=False)                           # '1'..'22', 'X', 'Y', 'MT'
    pos = Column(Integer, nullable=False)                            # Genomic position (GRCh38)
    ref = Column(String, nullable=False)                             # Reference allele
    alt = Column(String, nullable=False)                             # Alternate allele
    rsid = Column(String)                                            # dbSNP rsid (e.g. 'rs123456')
    variant_type = Column(String)                                    # SNV, indel, deletion, etc.

    # Minor allele info
    minor_allele = Column(String)                                    # Minor allele (from MA field)
    maf = Column(Float)                                              # Minor allele frequency (from MAF field)
    mac = Column(Integer)                                            # Minor allele count (from MAC field)
    ancestral_allele = Column(String)                                # Ancestral allele (from AA field)

    # Superpopulation allele frequencies
    af_afr = Column(Float)                                           # African
    af_amr = Column(Float)                                           # Admixed American
    af_eas = Column(Float)                                           # East Asian
    af_eur = Column(Float)                                           # European
    af_sas = Column(Float)                                           # South Asian

    # Evidence flags
    is_clinvar = Column(Boolean, default=False)                      # In ClinVar
    is_1000g = Column(Boolean, default=False)                        # In 1000 Genomes (always True here)

    # Source tracking
    data_source = Column(String, default='ensembl_vcf')             # 'ensembl_vcf'
    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_1kg_rsid', 'rsid'),
        Index('ix_1kg_chrom_pos', 'chrom', 'pos'),
        Index('ix_1kg_chrom_pos_ref_alt', 'chrom', 'pos', 'ref', 'alt', unique=True),
        Index('ix_1kg_maf', 'maf'),
    )


class DashboardCache(Base):
    """Pre-computed dashboard JSON per user.

    Refreshed when an analysis completes.  The endpoint reads one row
    instead of 18+ queries across 14 insight tables.
    """
    __tablename__ = 'dashboard_cache'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    dashboard_json = Column(JSON, nullable=False)
    analysis_fingerprint = Column(String, nullable=True)


class WorkerJob(Base):
    """Generic background job dispatched to the worker process.

    The worker polls for rows with status='pending' and executes them.
    Used for heavy tasks that should not block the API (e.g. auto-categorize).
    """
    __tablename__ = 'worker_jobs'

    id = Column(Integer, primary_key=True)
    job_type = Column(String, nullable=False, index=True)       # e.g. 'auto_categorize'
    status = Column(String, nullable=False, default='pending')   # pending → processing → completed / failed
    params = Column(JSON, nullable=True)                         # job-specific parameters
    result = Column(JSON, nullable=True)                         # output / stats on completion
    error = Column(Text, nullable=True)                          # error message on failure
    requested_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('ix_worker_jobs_status', 'status'),
    )
    refreshed_at = Column(DateTime(timezone=True), server_default=func.now())


class AiInsightCache(Base):
    """Persistent cache for AI-generated insights (panel sections and variant dialogs).

    cache_key format:
      - Panel:   "panel:{analysis_id}:{section}"
      - Variant: "variant:{rsid}"

    Rows are upserted on generation and returned on subsequent requests to avoid
    repeated LLM calls. Force-refresh deletes the row before regenerating.
    """
    __tablename__ = 'ai_insight_cache'

    id = Column(Integer, primary_key=True)
    cache_key = Column(String, unique=True, nullable=False, index=True)
    result = Column(JSON, nullable=False)
    provider = Column(String, nullable=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())