"""
TypedDict schemas for annotation JSON columns stored in SharedVariantAnnotation.

Each local/remote source produces a dict that is stored as JSON in the DB.
These TypedDicts define the expected shape so code accessing annotation data
gets IDE autocomplete and type-checking instead of untyped `.get()` chains.

Usage:
    from backend.db.annotation_schemas import ClinVarLocalAnnotation, GnomadAnnotation

    cv: ClinVarLocalAnnotation = annotation.clinvar_local_data
    if cv and cv.get('found'):
        print(cv['clinical_significances'])
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


# ─── Base ────────────────────────────────────────────────────────────

class NotFoundAnnotation(TypedDict):
    """Sentinel stored when a source confirms no data exists for a variant."""
    found: bool  # Always False
    source: str


# ─── ClinVar Local (PostgreSQL) ─────────────────────────────────────

class ClinVarGeneCondition(TypedDict):
    disease: str
    source: str
    source_id: str
    disease_mim: str


class ClinVarGeneStat(TypedDict):
    gene: str
    gene_id: str
    total_submissions: int
    total_alleles: int
    pathogenic_likely_pathogenic: int
    gene_mim: str
    uncertain: int
    with_conflicts: int


class ClinVarEntry(TypedDict, total=False):
    uid: Optional[int]
    allele_id: Optional[int]
    title: str
    accession: Optional[str]
    clinical_significance: List[str]
    conditions: List[str]
    variation_type: Optional[str]
    gene: Optional[str]
    review_status: Optional[str]
    origin: Optional[str]
    chromosome: Optional[str]
    start: str
    stop: str
    hgvs_nucleotide: str
    hgvs_protein: str


class ClinVarVcfData(TypedDict, total=False):
    allele_frequencies: Dict[str, float]  # {"exac": 0.01, "tgp": 0.02, "esp": 0.03}
    molecular_consequences: List[str]
    oncogenicity: List[str]
    somatic_clinical_impact: List[str]
    conflicting_classifications: List[str]


class ClinVarLocalAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.clinvar_local_data when found=True."""
    found: bool
    source: str  # "clinvar_local"
    count: int
    ids: List[int]
    allele_ids: List[int]
    clinical_significances: List[str]
    conditions: List[str]
    genes: List[str]
    review_statuses: List[str]
    has_conflicting_interpretations: bool
    total_submissions: int
    pubmed_ids: List[str]
    cross_references: List[str]
    gene_conditions: List[ClinVarGeneCondition]
    gene_stats: List[ClinVarGeneStat]
    disease_details: List[dict]
    entries: List[ClinVarEntry]
    vcf_data: ClinVarVcfData


# ─── gnomAD (PostgreSQL + SQLite cache + BigQuery) ──────────────────

class GnomadPopulationFreq(TypedDict):
    name: str
    af: float


class GnomadCaddScore(TypedDict, total=False):
    raw: Optional[float]
    phred: Optional[float]
    interpretation: Optional[str]


class GnomadPredictions(TypedDict, total=False):
    sift: Dict[str, Any]      # {"category": "deleterious", "score": 0.01}
    polyphen: Dict[str, Any]  # {"category": "probably_damaging", "score": 0.99}


class GnomadConservation(TypedDict, total=False):
    primate: Optional[float]
    mammal: Optional[float]
    vertebrate: Optional[float]


class GnomadSpliceAI(TypedDict, total=False):
    acceptor_gain: Optional[float]
    acceptor_loss: Optional[float]
    donor_gain: Optional[float]
    donor_loss: Optional[float]
    max_score: Optional[float]


class GnomadAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.gnomad_data when found=True."""
    found: bool
    source: str  # "gnomad_local", "gnomad_bigquery", "gnomad_tsv"
    rsid: Optional[str]
    chrom: str
    pos: int
    ref: str
    alt: str
    variant_id: str  # "chrom-pos-ref-alt"
    variant_type: Optional[str]  # "SNV", "INS", "DEL"
    filter_status: Optional[str]  # "PASS", etc.
    af: Optional[float]  # Global allele frequency
    ac: Optional[int]    # Global allele count
    an: Optional[int]    # Global allele number
    nhomalt: Optional[int]
    population_frequencies: Dict[str, GnomadPopulationFreq]
    gene: Optional[str]
    consequence: Optional[str]
    impact: Optional[str]  # "HIGH", "MODERATE", "LOW", "MODIFIER"
    hgvsc: Optional[str]
    hgvsp: Optional[str]
    cadd: GnomadCaddScore
    predictions: GnomadPredictions
    conservation: GnomadConservation
    splice_ai: GnomadSpliceAI
    other_alleles: List[Dict[str, Any]]  # Only present for multi-allelic sites


# ─── 1000 Genomes Phase 3 (PostgreSQL) ──────────────────────────────

class ThousandGenomesPopFreq(TypedDict):
    name: str
    af: float


class ThousandGenomesAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.thousand_genomes_data when found=True."""
    found: bool
    source: str  # "1000genomes_local"
    rsid: str
    chrom: str
    pos: int
    ref: str
    alt: str
    variant_type: Optional[str]
    minor_allele: Optional[str]
    maf: Optional[float]
    mac: Optional[int]
    ancestral_allele: Optional[str]
    population_frequencies: Dict[str, ThousandGenomesPopFreq]  # Keys: afr, amr, eas, eur, sas
    global_af: Optional[float]  # Approximate global AF (mean of population AFs)
    other_alleles: List[Dict[str, Any]]  # Only present for multi-allelic sites


# ─── Ensembl VEP (SQLite cache / remote API) ────────────────────────

class EnsemblTranscriptConsequence(TypedDict, total=False):
    consequence_terms: List[str]
    impact: str  # "HIGH", "MODERATE", "LOW", "MODIFIER"
    feature_type: Optional[str]  # "Transcript"
    transcript_id: Optional[str]
    gene_symbol: Optional[str]
    amino_acids: Optional[str]
    sift_prediction: Optional[str]
    sift_score: Optional[float]
    polyphen_prediction: Optional[str]
    polyphen_score: Optional[float]


class EnsemblColocatedVariant(TypedDict, total=False):
    id: str
    minor_allele: str
    minor_allele_freq: float
    frequencies: Dict[str, Dict[str, float]]


class EnsemblDataEntry(TypedDict, total=False):
    allele_string: str  # "A/G"
    seq_region_name: str  # chromosome
    start: int
    most_severe_consequence: Optional[str]
    transcript_consequences: List[EnsemblTranscriptConsequence]
    colocated_variants: List[EnsemblColocatedVariant]


class EnsemblAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.ensembl_data when found=True."""
    found: bool
    source: str  # "ensembl"
    data: List[EnsemblDataEntry]


# ─── AlphaMissense (tabix file) ─────────────────────────────────────

class AlphaMissenseAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.alpha_missense_data when found=True."""
    found: bool
    source: str  # "alpha_missense"
    chrom: str
    pos: int
    ref: str
    alt: str
    genome: str  # "hg38" or "hg19"
    uniprot_id: Optional[str]
    transcript_id: str
    protein_variant: str  # e.g. "A123T"
    am_pathogenicity: float  # 0.0–1.0
    am_class: Optional[str]  # "likely_benign", "ambiguous", "likely_pathogenic"


# ─── Remote API sources ─────────────────────────────────────────────

class ClinVarApiAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.clinvar_data (from ClinVar API)."""
    found: bool
    source: str  # "clinvar"
    data: Dict[str, Any]  # Raw ClinVar API response


class ClinPgxAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.pharmgkb_data (from ClinPGx API)."""
    found: bool
    source: str  # "clinpgx"
    data: Dict[str, Any]


class SnpediaAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.snpedia_data."""
    found: bool
    source: str  # "snpedia"
    data: Dict[str, Any]


class LitVarAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.litvar_data."""
    found: bool
    source: str  # "litvar"
    data: Dict[str, Any]


# ─── BigQuery sources ────────────────────────────────────────────────

class ChemblAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.chembl_data."""
    found: bool
    source: str  # "chembl"
    data: Dict[str, Any]


class FdaDrugAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.fda_drug_data."""
    found: bool
    source: str  # "fda_drug"
    data: Dict[str, Any]


class AlphaFoldAnnotation(TypedDict, total=False):
    """Shape of shared_variant_annotations.alphafold_data."""
    found: bool
    source: str  # "alphafold"
    data: Dict[str, Any]


# ─── Insight write-time validation ───

def validate_associated_variants(model_name: str, value: Any) -> None:
    """Reject malformed associated_variants payloads before they reach the DB.

    Every generate_from_maps-based insight row stores associated_variants as a
    list of rsid strings (e.g. ["rs123"]); a wrong shape here indicates a
    generator bug that would otherwise surface as a silent read-time failure.
    """
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(
            f"{model_name}.associated_variants must be a list of rsid strings, got {value!r}"
        )
