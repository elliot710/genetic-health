"""Core genetic-analysis models and per-analysis insight tables.

Split out of the former db/models.py module; see the package __init__.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON, Float, Index, BigInteger, SmallInteger, ARRAY, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.db.database import Base


class GeneticAnalysis(Base):
    __tablename__ = "genetic_analyses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
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
    completed_at = Column(DateTime(timezone=True), nullable=True)  # Set only on successful completion
    
    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Persisted job logs (JSON array of {ts, level, msg} entries)
    job_logs = Column(JSON, nullable=True)
    inferred_sex = Column(String(10), nullable=True)  # 'male', 'female', 'unknown'

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
    alt_alleles = Column(String, nullable=False, default='')  # Comma-separated list of all observed alt alleles
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
    genotype = Column(String, nullable=False, default='./.')
    quality = Column(String)
    filter_status = Column(String)
    info = Column(JSON, nullable=False, default=dict)
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
    risk_score = Column(Float, nullable=True)
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
