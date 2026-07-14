"""Variant-annotation tables and admin annotation config.

Split out of the former db/models.py module; see the package __init__.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON, Float, Index, BigInteger, SmallInteger, ARRAY, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.db.database import Base


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
    gwas_catalog_data = Column(JSON)  # GWAS Catalog trait associations (local TSV)
    clingen_data = Column(JSON)  # ClinGen gene validity classifications (local TSV)
    open_targets_data = Column(JSON)  # Open Targets Platform gene-disease association scores (API)
    
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
