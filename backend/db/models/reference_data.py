"""Reference/ETL source tables plus runtime cache and job tables.

Split out of the former db/models.py module; see the package __init__.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON, Float, Index, BigInteger, SmallInteger, ARRAY, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.db.database import Base


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


class GnomadV2Variant(Base):
    """gnomAD v2.1.1 exome variant — population AFs from per-chromosome VCFs (GRCh37).
    Primary lookup table for gnomAD population frequency data."""
    __tablename__ = "gnomad_v2_variants"

    id = Column(BigInteger, primary_key=True)
    chrom = Column(String, nullable=False)
    pos = Column(Integer, nullable=False)
    ref = Column(String, nullable=False)
    alt = Column(String, nullable=False)
    rsid = Column(String)
    af = Column(Float)
    af_afr = Column(Float)
    af_amr = Column(Float)
    af_eas = Column(Float)
    af_nfe = Column(Float)
    af_sas = Column(Float)
    af_fin = Column(Float)
    af_asj = Column(Float)
    ac = Column(Integer)
    an = Column(Integer)
    data_source = Column(String, default='gnomad_v2_vcf')
    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_gnomad_v2_rsid', 'rsid'),
        Index('ix_gnomad_v2_chrom_pos', 'chrom', 'pos'),
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
    job_logs = Column(JSON, nullable=True)

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


class GwasCatalogAssociation(Base):
    """GWAS Catalog variant-trait associations imported from the EBI full download."""
    __tablename__ = 'gwas_catalog_associations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rsid = Column(Text, nullable=True, index=True)
    pubmed_id = Column(Text, nullable=True)
    study_accession = Column(Text, nullable=True)
    trait = Column(Text, nullable=True)
    mapped_trait = Column(Text, nullable=True)
    mapped_trait_uri = Column(Text, nullable=True)
    reported_genes = Column(Text, nullable=True)
    mapped_genes = Column(Text, nullable=True)
    p_value = Column(Float, nullable=True)
    p_value_mlog = Column(Float, nullable=True)
    or_beta = Column(Float, nullable=True)
    ci_text = Column(Text, nullable=True)
    risk_allele_frequency = Column(Float, nullable=True)
    strongest_snp_risk_allele = Column(Text, nullable=True)
    chromosome = Column(Text, nullable=True)
    chromosome_position = Column(Integer, nullable=True)
    context = Column(Text, nullable=True)
    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_gwas_catalog_rsid', 'rsid'),
    )


class ClinGenGeneValidity(Base):
    """ClinGen gene-disease validity classifications."""
    __tablename__ = 'clingen_gene_validity'

    id = Column(Integer, primary_key=True, autoincrement=True)
    gene_symbol = Column(String(64), nullable=False, index=True)
    gene_hgnc_id = Column(String(32), nullable=True)
    disease_label = Column(Text, nullable=True)
    disease_mondo_id = Column(String(32), nullable=True)
    moi = Column(String(64), nullable=True)
    classification = Column(String(64), nullable=True)
    classification_date = Column(String(32), nullable=True)
    gcep = Column(Text, nullable=True)
    report_url = Column(Text, nullable=True)
    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_clingen_gene_symbol', 'gene_symbol'),
    )


class OpenTargetsCache(Base):
    __tablename__ = 'open_targets_cache'

    gene_symbol = Column(String(50), primary_key=True)
    data = Column(JSON, nullable=False)
