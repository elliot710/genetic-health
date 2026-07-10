"""
Shared context, helpers, and generic map-driven generator used by all
insight generator modules.
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...db.annotation_schemas import validate_associated_variants
from ...db.models import AnalysisVariant

logger = logging.getLogger(__name__)

_BENIGN_CLASSIFICATIONS = frozenset(('benign', 'likely_benign'))


# ---------------------------------------------------------------------------
# Variant profile — pre-computed per-variant enrichment
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class VariantProfile:
    """Pre-computed per-variant data extracted ONCE and shared by all generators.

    This is the single source of truth for variant-level attributes during
    insight generation.  Generators should read from profiles rather than
    re-extracting from raw annotation JSON — ensuring consistent ref allele
    resolution, frequency handling, and zygosity classification everywhere.
    """
    rsid: str
    genotype: Optional[str]
    effective_ref: Optional[str]
    gene: Optional[str]
    consequence: Optional[str]
    impact: Optional[str]
    chromosome: Optional[str]
    # None = no frequency data available.  0.0 = monomorphic (not the same!).
    population_frequency: Optional[float]
    clinical_significance: Optional[str]   # First ClinVar sig, lowercased
    is_benign: bool
    is_hom_ref: bool
    is_het: bool
    is_no_call: bool
    composite_score: float
    pathogenicity_score: Optional[dict]
    annotation_result: Any   # AnnotationResult reference for generator-specific needs
    variant: Any             # VariantLite reference


# ---------------------------------------------------------------------------
# Shared context object passed to every generator
# ---------------------------------------------------------------------------

@dataclass
class GeneratorContext:
    """Immutable bag of data every insight generator needs."""
    analysis_id: int
    variants: List[AnalysisVariant]
    annotation_results: Dict[str, Any]  # rsid -> AnnotationResult
    session: AsyncSession
    rsid_gene_map: Dict[str, str]       # rsid -> gene symbol
    registry: Dict[str, Dict[str, Dict]]  # category -> {rsid: {}, gene: {}}
    variant_profiles: Dict[str, VariantProfile] = field(default_factory=dict)
    inferred_sex: Optional[str] = None  # 'male', 'female', 'unknown'

    def get_maps(self, category: str):
        """Return (rsid_map, gene_map) for a category from the loaded registry."""
        maps = self.registry.get(category, {'rsid': {}, 'gene': {}})
        return maps['rsid'], maps['gene']


# ---------------------------------------------------------------------------
# Annotation extraction helpers (pure functions, no DB access)
# ---------------------------------------------------------------------------

def extract_gene_and_consequence(
    annotation_result,
    rsid_gene_map: Dict[str, str],
):
    """Extract gene symbol and consequence from annotation data.
    Falls back to ClinVar DB rsid->gene map when Ensembl data is unavailable."""
    if not annotation_result or not annotation_result.annotation_data:
        if annotation_result and annotation_result.rsid:
            gene = rsid_gene_map.get(annotation_result.rsid)
            if gene:
                return gene, None, None
        return None, None, None

    try:
        # 1. Try Ensembl
        ensembl_data = annotation_result.annotation_data.get('annotations', {}).get('ensembl', {})
        if ensembl_data:
            data_list = ensembl_data.get('data', [])
            if data_list:
                entry = data_list[0]
                transcript_consequences = entry.get('transcript_consequences', [])
                if transcript_consequences:
                    tc = transcript_consequences[0]
                    gene = tc.get('gene_symbol')
                    consequence = (tc.get('consequence_terms') or [None])[0]
                    impact = tc.get('impact')
                    # Always extract consequence even when gene_symbol is absent.
                    # Local VEP VCF files use a simplified CSQ format that omits SYMBOL,
                    # so we fall back to rsid_gene_map for the gene name.
                    if consequence or gene:
                        if not gene and annotation_result.rsid:
                            gene = rsid_gene_map.get(annotation_result.rsid)
                        return gene, consequence, impact

        # 2. Try ClinVar local annotation data
        cv_local = annotation_result.annotation_data.get('annotations', {}).get('clinvar_local', {})
        if cv_local and cv_local.get('found'):
            genes = cv_local.get('genes', [])
            if genes:
                return genes[0], cv_local.get('molecular_consequence'), None

        # 3. Try gnomAD annotation data
        gnomad = annotation_result.annotation_data.get('annotations', {}).get('gnomad', {})
        if gnomad and gnomad.get('found') and gnomad.get('gene'):
            return gnomad['gene'], gnomad.get('consequence'), gnomad.get('impact')

        # 4. Fallback: ClinVar DB rsid->gene map
        gene = rsid_gene_map.get(annotation_result.rsid)
        if gene:
            return gene, None, None

        return None, None, None
    except (KeyError, IndexError, TypeError):
        return None, None, None


def extract_frequency(annotation_result) -> float:
    """Extract population frequency from annotation data.

    Tries multiple sources in order:
    1. Ensembl VEP colocated_variants gnomAD frequencies
    2. gnomAD local allele frequency (af)
    3. 1000 Genomes global allele frequency
    """
    if not annotation_result or not annotation_result.annotation_data:
        return 0.0

    annotations = annotation_result.annotation_data.get('annotations', {})

    try:
        # 1. Ensembl VEP
        ensembl_data = annotations.get('ensembl', {})
        data_list = ensembl_data.get('data', [])
        if data_list:
            entry = data_list[0]
            freqs = entry.get('colocated_variants', [{}])[0].get('frequencies', {})
            if freqs:
                first_allele = next(iter(freqs.values()), {})
                val = first_allele.get('gnomade', first_allele.get('gnomad', 0.0))
                if val:
                    return val
    except (KeyError, IndexError, TypeError, StopIteration):
        pass

    try:
        # 2. gnomAD local
        gnomad = annotations.get('gnomad', {})
        if gnomad and gnomad.get('found'):
            af = gnomad.get('af')
            if af is not None and af > 0:
                return af
    except (KeyError, TypeError):
        pass

    try:
        # 3. 1000 Genomes — use the global allele frequency
        tkg = annotations.get('thousand_genomes', {})
        if tkg and tkg.get('found'):
            af_global = tkg.get('global_af') or tkg.get('af_global') or tkg.get('maf')
            if af_global is not None and af_global > 0:
                return af_global
    except (KeyError, TypeError):
        pass

    return 0.0


def get_ref_allele(variant) -> Optional[str]:
    """Extract the reference allele from the variant's marker."""
    marker = getattr(variant, 'marker', None)
    if marker:
        ref = getattr(marker, 'ref_allele', None)
        if ref and ref not in ('N', '-', '.', ''):
            return ref
    return None


def get_annotation_ref_allele(annotation_result) -> Optional[str]:
    """Extract the reference allele from annotation data (ClinVar local, Ensembl, gnomAD).

    More reliable than the marker's ref_allele for consumer CSV data where
    ref_allele == alt_alleles ~83% of the time.
    """
    if not annotation_result or not annotation_result.annotation_data:
        return None

    annotations = annotation_result.annotation_data.get('annotations', {})

    # ClinVar local — has explicit ref/alt alleles
    cv = annotations.get('clinvar_local', {})
    if cv and cv.get('found'):
        ref = cv.get('ref_allele') or cv.get('reference_allele')
        if ref and ref not in ('N', '-', '.', ''):
            return ref.strip().upper()

    # Ensembl VEP — allele_string format: "REF/ALT"
    ensembl = annotations.get('ensembl', {})
    data_list = ensembl.get('data', [])
    if data_list:
        allele_str = data_list[0].get('allele_string', '')
        if '/' in allele_str:
            ref = allele_str.split('/')[0].strip()
            if ref and ref not in ('N', '-', '.', ''):
                return ref.upper()

    # gnomAD — has ref column
    gnomad = annotations.get('gnomad', {})
    if gnomad and gnomad.get('found'):
        ref = gnomad.get('ref')
        if ref and ref not in ('N', '-', '.', ''):
            return ref.strip().upper()

    return None


def get_annotation_allele_parts(annotation_result) -> tuple:
    """Return (ref, alt) alleles from annotations, including '-' for indels.

    Unlike get_annotation_ref_allele(), this does NOT filter out '-' chars,
    so callers can distinguish insertion vs deletion variants for correct
    consumer D/I code interpretation.
    """
    if not annotation_result or not annotation_result.annotation_data:
        return (None, None)

    annotations = annotation_result.annotation_data.get('annotations', {})

    # Ensembl VEP — allele_string format: "REF/ALT" or "REF/ALT1,ALT2"
    # For multi-allelic sites (REF/ALT1,ALT2) we return ALL alts joined so
    # callers can check if the user carries ANY of the risk alleles at this
    # position, not just the arbitrarily-first one.
    ensembl = annotations.get('ensembl', {})
    data_list = ensembl.get('data', [])
    if data_list:
        allele_str = data_list[0].get('allele_string', '')
        if '/' in allele_str:
            parts = allele_str.split('/', 1)
            ref = parts[0].strip()
            alt = parts[1].strip()  # Keep full alt string, may be "A,T" for multi-allelic
            if ref and alt:
                return (ref.upper(), alt.upper())

    # gnomAD — has ref and alt columns (single alt)
    gnomad = annotations.get('gnomad', {})
    if gnomad and gnomad.get('found'):
        ref = gnomad.get('ref', '')
        alt = gnomad.get('alt', '')
        if ref and alt:
            return (ref.strip().upper(), alt.strip().upper())

    # ClinVar local — has explicit ref/alt alleles (single alt)
    cv = annotations.get('clinvar_local', {})
    if cv and cv.get('found'):
        ref = cv.get('ref_allele') or cv.get('reference_allele') or ''
        alt = cv.get('alt_allele') or cv.get('alternate_allele') or ''
        if ref and alt:
            return (ref.strip().upper(), alt.strip().upper())

    return (None, None)


def indel_d_is_ref(ref_allele: str | None, alt_allele: str | None) -> bool | None:
    """For consumer D/I indel codes, determine if D maps to the reference allele.

    D = shorter/deletion allele, I = longer/insertion allele.
    Returns True if D=ref (insertion variant), False if D=alt (deletion variant),
    None if we can't determine.
    """
    if not ref_allele or not alt_allele:
        return None
    # BUG-03: treat 'N' (unknown nucleotide placeholder from consumer CSVs)
    # the same as '-' / '.' — we cannot infer allele lengths from it.
    _UNKNOWN = ('-', '.', 'N')
    ref_up = ref_allele.strip().upper()
    alt_up = alt_allele.strip().upper()
    # For multi-allelic sites (e.g. "C,CCC" from allele_string "CC/C,CCC"),
    # use only the first alt allele for length comparison. This matches the
    # VariantDetailDialog.tsx frontend behaviour (alts[0]). Without this,
    # the full comma-joined string length is used, producing incorrect D/I
    # directionality for dual-allele consumer array variants (BUG-14).
    if ',' in alt_up:
        alt_up = alt_up.split(',')[0].strip()
    if ref_up in _UNKNOWN or alt_up in _UNKNOWN:
        return None
    ref_len = len(ref_up)
    alt_len = len(alt_up)
    if ref_len == alt_len:
        return None  # Not an indel or ambiguous
    return ref_len <= alt_len  # D = shorter allele; if ref is shorter, D=ref


def _get_effective_ref_allele(variant, annotation_result) -> Optional[str]:
    """Get the best available reference allele for a variant.

    Prefers annotation-derived ref (authoritative) over marker-derived ref.
    Discards marker ref when it equals marker alt (ambiguous consumer CSV data).
    """
    ann_ref = get_annotation_ref_allele(annotation_result)
    if ann_ref:
        return ann_ref

    marker = getattr(variant, 'marker', None)
    if not marker:
        return None
    marker_ref = getattr(marker, 'ref_allele', None)
    if not marker_ref or marker_ref in ('N', '-', '.', ''):
        return None
    # Don't trust marker ref if it equals alt (ambiguous consumer CSV)
    marker_alt = getattr(marker, 'alt_alleles', None) or ''
    if marker_ref.strip().upper() == marker_alt.strip().upper():
        return None
    return marker_ref.strip().upper()


def risk_level_to_score(risk_level: str) -> float:
    """Convert a risk level string to a numeric 0–1 score for storage and comparison."""
    _SCORES = {
        'low': 0.2,
        'average': 0.4,
        'moderate': 0.6,
        'high': 0.8,
        'very_high': 0.95,
        'unknown': 0.0,
    }
    return _SCORES.get(risk_level.strip().lower().replace(' ', '_'), 0.5)


def get_user_genotype(variant) -> Optional[str]:
    """Extract the user's genotype from the variant.

    Checks the dedicated ``genotype`` column first, then falls back to
    ``info.original_genotype`` (older CSV uploads stored it there).
    """
    gt = getattr(variant, 'genotype', None)
    if gt:
        return gt.strip().upper()
    info = getattr(variant, 'info', None)
    if isinstance(info, dict):
        og = info.get('original_genotype')
        if og:
            return str(og).strip().upper()
    return None


# Consumer array genotype codes for indels (insertions/deletions).
# These are NOT nucleotide alleles — they indicate structural variant status.
#   II = insertion/insertion = homozygous reference (user has the reference sequence)
#   DD = deletion/deletion = homozygous alternate (user carries the deletion)
#   DI or ID = heterozygous (one deleted copy, one reference copy)
#   -- = no call / failed genotyping
_INDEL_CODES = frozenset({'II', 'DD', 'DI', 'ID'})
_NO_CALL_CODES = frozenset({'--', '00', 'NC', './.', '.|.'})

# ClinVar significance values that indicate a variant is NOT clinically
# harmful. Used to filter out benign variants at insight generation time
# as a defence-in-depth check (the auto-categorizer should also exclude
# these, but manually-seeded mappings may not have been vetted).
_BENIGN_SIG_PREFIXES = ('benign', 'likely benign', 'likely_benign')


def _get_all_clinvar_significances(annotations: dict) -> list:
    sigs: list = []
    cv_local = annotations.get('clinvar_local', {})
    if cv_local and cv_local.get('found'):
        sigs.extend(cv_local.get('clinical_significances', []))
    cv_api = annotations.get('clinvar', {})
    if cv_api and cv_api.get('found'):
        for entry in cv_api.get('entries', []):
            entry_sigs = entry.get('clinical_significance', [])
            sigs.extend([entry_sigs] if isinstance(entry_sigs, str) else entry_sigs)
        top_sig = cv_api.get('clinical_significance', '')
        if isinstance(top_sig, str) and top_sig:
            sigs.append(top_sig)
    return sigs


def _has_computational_pathogenicity(annotations: dict) -> bool:
    am = annotations.get('alpha_missense', {})
    if am and am.get('found'):
        am_class = (am.get('am_class') or am.get('classification') or '').lower()
        if 'pathogenic' in am_class:
            return True
    gnomad = annotations.get('gnomad', {})
    if gnomad and gnomad.get('found'):
        cadd = gnomad.get('cadd', {})
        if isinstance(cadd, dict) and cadd.get('phred') is not None:
            if cadd['phred'] >= 25:
                return True
    return False


def is_clinvar_benign(annotation_result) -> bool:
    """Return True when ALL available annotation sources agree the variant is benign.

    Cross-references ClinVar local, ClinVar API, and computational predictors
    (AlphaMissense, CADD) to avoid filtering variants where any source reports
    potential pathogenicity.
    """
    if not annotation_result or not annotation_result.annotation_data:
        return False
    annotations = annotation_result.annotation_data.get('annotations', {})

    cv_sigs_all = _get_all_clinvar_significances(annotations)
    if not cv_sigs_all:
        return False

    for sig in cv_sigs_all:
        s = sig.strip().lower().replace('_', ' ')
        if s and not any(s.startswith(prefix) for prefix in _BENIGN_SIG_PREFIXES):
            return False

    return not _has_computational_pathogenicity(annotations)


def is_indel_genotype(genotype: Optional[str]) -> bool:
    """True when genotype uses consumer array indel codes (II/DD/DI/ID)."""
    if not genotype:
        return False
    return genotype.strip().upper() in _INDEL_CODES


def is_no_call_genotype(genotype: Optional[str]) -> bool:
    """True when genotype represents a failed or missing call."""
    if not genotype:
        return True
    gt = genotype.strip().upper()
    return gt in _NO_CALL_CODES or gt == ''


def _parse_alleles(genotype: Optional[str]):
    """Split a genotype string into a list of alleles, or return None.
    
    For hemizygous genotypes (single allele, e.g. X chromosome in males),
    returns a single-element list so callers can handle it.

    Consumer array indel codes (II, DD, DI, ID) are returned as-is
    since they are not nucleotide alleles.  Callers should use
    is_indel_genotype() to detect these before allele-level logic.
    """
    if not genotype:
        return None
    gt = genotype.strip().upper()
    # No-call or empty
    if gt in _NO_CALL_CODES or not gt:
        return None
    # Consumer array indel codes — return the code letters as "alleles"
    # so that II → ['I', 'I'], DD → ['D', 'D'], DI → ['D', 'I']
    if gt in _INDEL_CODES:
        return [gt[0], gt[1]]
    if '/' in gt:
        alleles = gt.split('/')
    elif '|' in gt:
        alleles = gt.split('|')
    elif len(gt) == 2:
        alleles = [gt[0], gt[1]]
    elif len(gt) == 1:
        return [gt]  # hemizygous (X chromosome, mitochondrial)
    else:
        return None
    return alleles if len(alleles) >= 1 else None


def is_homozygous_reference(genotype: Optional[str], ref_allele: Optional[str] = None,
                            alt_allele: Optional[str] = None) -> bool:
    """Return True when the user carries only the reference allele.

    Handles diploid (2 alleles) and hemizygous (1 allele, e.g. X chromosome in males).

    Consumer array indel codes (D=shorter, I=longer):
      For insertion variants (ref shorter than alt): DD=hom-ref, II=hom-alt
      For deletion variants (ref longer than alt):   II=hom-ref, DD=hom-alt
      DI/ID always = heterozygous

    When *alt_allele* is provided alongside *ref_allele*, the function uses
    allele length comparison to correctly interpret D/I codes.
    """
    if not genotype:
        return False
    gt = genotype.strip().upper()
    # No-call → not reference
    if gt in _NO_CALL_CODES:
        return False
    # Consumer array indel codes — use allele lengths when available
    if gt in _INDEL_CODES:
        d_ref = indel_d_is_ref(ref_allele, alt_allele)
        if d_ref is True:
            # Insertion variant: D=ref, I=alt
            return gt == 'DD'
        elif d_ref is False:
            # Deletion variant: I=ref, D=alt
            return gt == 'II'
        else:
            # Unknown allele lengths — can't determine, return False (conservative)
            return False
    alleles = _parse_alleles(genotype)
    if alleles is None:
        return False
    if ref_allele:
        ref = ref_allele.strip().upper()
        return all(a == ref for a in alleles)
    # Without ref_allele we cannot distinguish homozygous-reference from
    # homozygous-alternate.  Return False to avoid silently skipping
    # variants that might be homozygous for the risk allele.
    return False


def is_heterozygous(genotype: Optional[str]) -> bool:
    """Return True when the genotype has two different alleles.
    Hemizygous genotypes (1 allele) are never heterozygous."""
    if not genotype:
        return False
    gt = genotype.strip().upper()
    # Consumer array indel codes
    if gt in ('DI', 'ID'):
        return True   # one deletion, one insertion = het
    if gt in ('II', 'DD') or gt in _NO_CALL_CODES:
        return False
    alleles = _parse_alleles(genotype)
    if alleles is None or len(alleles) < 2:
        return False
    return alleles[0] != alleles[1]


# Severity ladder used by zygosity_adjust — from mildest to most severe
_SEVERITY_LADDER = ['low', 'average', 'moderate', 'high', 'very_high']
_SEVERITY_IDX = {v: i for i, v in enumerate(_SEVERITY_LADDER)}

# Map common auto-categorizer values to ladder equivalents so zygosity
# adjustment actually works for auto-generated mappings.
_LEVEL_ALIASES = {
    'variable': 'average',
    'reduced': 'moderate',
    'elevated': 'high',
    'elevated risk': 'high',
    'elevated_risk': 'high',
    'normal': 'average',
    # Auto-categorizer values missing from previous version (BUG-06)
    'mildly_reduced': 'average',
    'b12_dependent': 'moderate',
    'slow_processing': 'moderate',
    'variant_detected': 'moderate',
    'sensitive': 'moderate',
}


def zygosity_adjust(level: str, genotype: Optional[str], *, ref_allele: Optional[str] = None, steps: int = 1) -> str:
    """Shift a severity/level string up or down based on zygosity.

    - Homozygous reference (both alleles == ref): de-escalate by *steps*
    - Heterozygous (one alternate allele): keep as-is (the mapping baseline)
    - Homozygous alternate (both alleles != ref): escalate by *steps*

    When *ref_allele* is supplied the classification is exact.
    Without it the function uses a heuristic (any homozygous → reference).
    """
    normalised = level.strip().lower().replace(' ', '_')
    # Resolve aliases so auto-generated values participate in the ladder
    resolved = _LEVEL_ALIASES.get(normalised, normalised)
    idx = _SEVERITY_IDX.get(resolved)
    if idx is None:
        logger.debug(
            "zygosity_adjust: unrecognised level %r (resolved %r) — returning unchanged",
            level, resolved,
        )
        return level  # not on the ladder — nothing to shift

    if not genotype or is_no_call_genotype(genotype):
        new_idx = idx  # Missing/no-call genotype → preserve baseline (don't de-escalate)
    elif is_homozygous_reference(genotype, ref_allele):
        new_idx = max(0, idx - steps)
    elif is_heterozygous(genotype):
        new_idx = idx  # baseline — no change
    else:
        # Homozygous non-reference. Escalate ONLY when we can positively
        # confirm the genotype is non-reference — i.e. ref_allele is known
        # and the genotype is a resolvable nucleotide homozygote. When the
        # reference is unknown (or the genotype is an indel D/I code with no
        # allele-direction data), we cannot distinguish hom-alt from hom-ref,
        # so preserve baseline rather than fabricating an escalation that
        # inflates risk from missing data (U3/KTD3 — conservative policy).
        if ref_allele and not is_indel_genotype(genotype):
            new_idx = min(len(_SEVERITY_LADDER) - 1, idx + steps)
        else:
            new_idx = idx

    result = _SEVERITY_LADDER[new_idx]
    # Preserve original casing style (Title Case if original was)
    if level[0].isupper():
        result = result.replace('_', ' ').title()
    return result


# ---------------------------------------------------------------------------
# Scoring / recommendation helpers
# ---------------------------------------------------------------------------

def boost_if_pathogenic(level: str, pathogenicity_score: Optional[Dict]) -> str:
    """Escalate a trait/risk level by one step when composite score >= 0.80.

    Used by non-health generators (sports, nutrition, wellness, …) so that a
    ClinVar-confirmed pathogenic variant at a mapped locus generates a higher
    trait level than the registry default — without invoking the full
    assess_risk_level() logic (which requires a risk_multiplier).

    BUG-13 fix: this bridges the gap between zygosity_adjust() (which only
    considers genotype) and pathogenicity-aware scoring.
    """
    if not pathogenicity_score or not isinstance(pathogenicity_score, dict):
        return level
    composite = pathogenicity_score.get('composite_score', 0.0)
    if composite < 0.80:
        return level
    normalised = level.strip().lower().replace(' ', '_')
    resolved = _LEVEL_ALIASES.get(normalised, normalised)
    idx = _SEVERITY_IDX.get(resolved)
    if idx is None:
        return level  # not on ladder — cannot escalate
    new_idx = min(len(_SEVERITY_LADDER) - 1, idx + 1)
    result = _SEVERITY_LADDER[new_idx]
    # Preserve casing style
    if level and level[0].isupper():
        result = result.replace('_', ' ').title()
    return result


def assess_risk_level(genotype: str, risk_multiplier: float, ref_allele: Optional[str] = None,
                      pathogenicity_score: Optional[Dict] = None) -> str:
    """Assess risk level considering the risk multiplier, zygosity, and
    optionally the composite pathogenicity score from the scoring engine."""
    if not genotype or is_no_call_genotype(genotype):
        return 'unknown'

    # If we have a scoring engine result, blend it with the static multiplier
    if pathogenicity_score and isinstance(pathogenicity_score, dict):
        composite = pathogenicity_score.get('composite_score', 0.0)
        if composite >= 0.80:
            base = 'high'
        elif composite >= 0.60:
            base = 'high' if risk_multiplier >= 2.0 else 'moderate'
        elif composite >= 0.30:
            base = 'moderate' if risk_multiplier >= 2.0 else 'average'
        else:
            # Low pathogenicity — use multiplier-based thresholds
            if risk_multiplier >= 2.0:
                base = 'moderate'  # Downgrade from 'high' if scoring says benign
            elif risk_multiplier >= 1.2:
                base = 'low'
            else:
                base = 'low'
    else:
        # Fallback: multiplier-only — cap at 'moderate', never 'high'.
        # 'high' requires evidence from the composite pathogenicity score
        # (ClinVar + gnomAD + AlphaMissense); a population risk multiplier
        # alone is insufficient to justify the highest risk category.
        if risk_multiplier >= 1.2:
            base = 'moderate'
        elif risk_multiplier <= 0.8:
            base = 'low'
        else:
            base = 'average'
    # Adjust for zygosity
    return zygosity_adjust(base, genotype, ref_allele=ref_allele)


def assess_drug_response(genotype: str, gene: str, ref_allele: Optional[str] = None) -> str:
    """Assess drug response considering star alleles AND common rsid genotypes.

    Consumer genetic data uses rsid genotypes (A/G, C/T) rather than
    CYP star alleles.  For well-known pharmacogenes we use genotype-based
    heuristics:
    - Homozygous reference → normal metabolizer
    - Heterozygous at a known pharmacogene → intermediate metabolizer
    - Homozygous non-reference → poor metabolizer
    """
    if not genotype or is_no_call_genotype(genotype):
        return 'normal'

    # If user is homozygous reference, they metabolize normally
    if ref_allele and is_homozygous_reference(genotype, ref_allele):
        return 'normal'

    gt_upper = genotype.upper().replace('/', '')

    # Star-allele patterns (from VCF or curated data)
    if gene == 'CYP2C9' and ('*2' in genotype or '*3' in genotype):
        return 'poor'
    elif gene == 'CYP2C19' and '*2' in genotype:
        return 'poor'

    # Consumer rsid genotype heuristic for pharmacogenes:
    # If user is heterozygous at a pharmacogene variant → intermediate
    # If user is homozygous non-reference → poor metabolizer
    pharmacogenes = {
        'CYP2D6', 'CYP2C19', 'CYP2C9', 'CYP3A4', 'CYP3A5', 'CYP1A2',
        'CYP2B6', 'DPYD', 'TPMT', 'UGT1A1', 'NUDT15', 'SLCO1B1',
        'VKORC1', 'NAT2', 'CYP2A6', 'CYP4F2', 'G6PD',
    }
    if gene in pharmacogenes and len(gt_upper) == 2:
        if gt_upper[0] != gt_upper[1]:
            return 'intermediate'
        else:
            # Homozygous. Call 'poor' ONLY when we can confirm the genotype is
            # non-reference: a confirmed hom-ref already returned 'normal'
            # above, so a KNOWN ref reaching here means genuine hom-alt. With
            # an unknown reference we cannot distinguish hom-alt from hom-ref,
            # so do not fabricate a poor-metabolizer call from missing data
            # (U3/KTD3 — conservative policy).
            if ref_allele:
                return 'poor'
            return 'normal'
    return 'normal'


def get_health_recommendations(condition: str, risk_level: str) -> List[str]:
    base = {
        'Type 2 Diabetes': [
            'Monitor blood glucose regularly', 'Maintain healthy weight',
            'Exercise regularly', 'Consider genetic counseling'
        ],
        'Cardiovascular Disease': [
            'Monitor blood pressure', 'Maintain healthy cholesterol levels',
            'Exercise regularly', 'Consider cardiology consultation'
        ]
    }
    return base.get(condition, ['Consult with healthcare provider'])


def get_drug_recommendations(drug: str, response_type: str) -> str:
    if response_type == 'poor':
        return f"Consider alternative to {drug} or adjusted dosing"
    elif response_type == 'intermediate':
        return f"Monitor {drug} response closely"
    return f"Standard {drug} dosing likely appropriate"


def get_trait_description(trait: str, result: str) -> str:
    return f"Genetic analysis indicates {result} for {trait}"


# ---------------------------------------------------------------------------
# Sex-linked condition filtering
# ---------------------------------------------------------------------------

_X_LINKED_FEMALE_ONLY_CONDITIONS = frozenset({
    'rett syndrome', 'atypical rett syndrome',
})

_X_LINKED_RECESSIVE_GENES = frozenset({
    'DMD', 'F8', 'F9', 'G6PD', 'OTC', 'AR', 'AVPR2', 'BTK',
    'CYBB', 'GJB1', 'IL2RG', 'LAMP2', 'PDHA1', 'PLP1', 'SLC16A2',
})


def should_skip_sex_linked(
    rsid: str,
    condition: str,
    gene: Optional[str],
    chromosome: Optional[str],
    inferred_sex: Optional[str],
) -> bool:
    if not inferred_sex or inferred_sex == 'unknown':
        return False
    if not chromosome or chromosome.upper() not in ('X', 'CHRX'):
        return False
    condition_lower = condition.lower().strip()
    if inferred_sex == 'male' and condition_lower in _X_LINKED_FEMALE_ONLY_CONDITIONS:
        return True
    return False


# ---------------------------------------------------------------------------
# GWAS trait → insight category mapping
# ---------------------------------------------------------------------------

_GWAS_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    'cognitive': [
        'intelligence', 'cognitive', 'educational attainment',
        'general cognitive ability', 'fluid intelligence', 'reaction time',
        'memory', 'cognitive performance',
    ],
    'personality': [
        'neuroticism', 'extraversion', 'openness', 'conscientiousness',
        'agreeableness', 'adventurousness', 'risk-taking', 'risk taking',
        'loneliness', 'well-being', 'wellbeing', 'happiness',
        'personality', 'subjective well-being',
    ],
    'sports': [
        'grip strength', 'muscle', 'endurance', 'sprint',
        'athletic', 'physical activity', 'exercise',
        'hand grip strength', 'vo2 max',
    ],
    'physical': [
        'height', 'eye color', 'hair color', 'skin pigmentation',
        'freckles', 'male pattern baldness', 'body mass index',
        'waist', 'hip circumference',
    ],
    'nutrition': [
        'caffeine', 'lactose', 'vitamin', 'omega', 'folate',
        'alcohol consumption', 'bitter taste', 'fatty acid',
        'iron levels', 'zinc', 'selenium',
    ],
    'wellness': [
        'sleep duration', 'insomnia', 'circadian', 'chronotype',
        'longevity', 'telomere length', 'biological aging',
        'morningness', 'stress',
    ],
}


def classify_gwas_trait(trait: str) -> Optional[str]:
    trait_lower = trait.lower()
    for category, keywords in _GWAS_CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in trait_lower:
                return category
    return None


def extract_gwas_insights(annotation_result) -> List[Dict[str, Any]]:
    if not annotation_result or not annotation_result.annotation_data:
        return []
    gwas = annotation_result.annotation_data.get('annotations', {}).get('gwas_catalog', {})
    if not gwas or not gwas.get('found'):
        return []
    insights = []
    seen_categories: set = set()
    for assoc in gwas.get('associations', []):
        p_value = assoc.get('p_value')
        if p_value is None or p_value > 5e-8:
            continue
        trait = assoc.get('trait', '')
        category = classify_gwas_trait(trait)
        if category and category not in seen_categories:
            seen_categories.add(category)
            insights.append({
                'category': category,
                'trait': trait,
                'p_value': p_value,
                'p_value_mlog': assoc.get('p_value_mlog'),
                'study_accession': assoc.get('study_accession'),
                'risk_allele_frequency': assoc.get('risk_allele_frequency'),
            })
    return insights


# ---------------------------------------------------------------------------
# ClinGen gene-disease validity check
# ---------------------------------------------------------------------------

def get_clingen_validity(annotation_result) -> Optional[str]:
    if not annotation_result or not annotation_result.annotation_data:
        return None
    clingen = annotation_result.annotation_data.get('annotations', {}).get('clingen', {})
    if not clingen or not clingen.get('found'):
        return None
    return clingen.get('strongest_classification')


# ---------------------------------------------------------------------------
# Generic map-driven generator
# ---------------------------------------------------------------------------

async def generate_from_maps(
    ctx: GeneratorContext,
    *,
    rsid_map: Dict,
    gene_map: Dict,
    dedup_field: str,
    build_from_rsid: Callable,
    build_from_gene: Callable,
    filter_benign: bool = False,
    skip_benign_filter: bool = False,
    max_population_af: Optional[float] = None,
) -> int:
    """
    Generic loop shared by most category generators.

    Args:
        rsid_map / gene_map: lookup dicts from variant_registry.
        dedup_field: key inside the info dict used to avoid duplicates.
        build_from_rsid(analysis_id, rsid, genotype, info) -> model | None
        build_from_gene(analysis_id, rsid, gene, consequence, info) -> model | None
        filter_benign: deprecated — kept for backward compat.
        skip_benign_filter: deprecated — use max_population_af instead.
        max_population_af: population allele frequency ceiling. Variants
            above this threshold are skipped unless ClinVar explicitly
            classifies them as pathogenic.  Clinical panels use 0.05,
            lifestyle panels use 0.20.  None disables the gate.
    """
    items = []
    seen: set = set()

    for _idx, variant in enumerate(ctx.variants):
        if _idx > 0 and _idx % 200 == 0:
            await asyncio.sleep(0)
        rsid = getattr(variant, 'rsid', None)
        if not rsid:
            continue

        # Extract genotype, ref allele, and annotation data early
        # (used by both rsid and gene matching).
        genotype = get_user_genotype(variant)
        if is_no_call_genotype(genotype):
            continue
        annotation_result = ctx.annotation_results.get(rsid)
        effective_ref = _get_effective_ref_allele(variant, annotation_result)

        # Get alt allele for proper indel D/I code interpretation
        _, _alt_allele = get_annotation_allele_parts(annotation_result)

        # Skip homozygous reference — user doesn't carry any risk allele
        # at this position. Other variants in the same gene can still match.
        if effective_ref and is_homozygous_reference(genotype, effective_ref, alt_allele=_alt_allele):
            continue

        # Population frequency gate — skip common variants that are too
        # frequent to be clinically meaningful.  Variants with strong
        # ClinVar pathogenic evidence bypass this gate.
        if max_population_af is not None:
            _prof = ctx.variant_profiles.get(rsid)
            _var_freq = _prof.population_frequency if _prof else extract_frequency(annotation_result)
            if _var_freq is not None and _var_freq > max_population_af:
                _has_clinvar_path = False
                if annotation_result and annotation_result.annotation_data:
                    _cv_sigs = _get_all_clinvar_significances(
                        annotation_result.annotation_data.get('annotations', {})
                    )
                    _has_clinvar_path = any(
                        'pathogenic' in s.lower() for s in _cv_sigs
                    )
                if not _has_clinvar_path:
                    continue

        # rsid-based matching
        if rsid in rsid_map:
            # Defence-in-depth: skip variants where ALL annotation sources
            # agree the variant is benign. This catches both auto-categorized
            # mappings that slipped through (e.g. "Conflicting" matched as
            # "Pathogenic") and manually-seeded mappings for variants that
            # ClinVar has since reclassified as benign.
            if is_clinvar_benign(annotation_result):
                continue

            info = rsid_map[rsid]

            # Sex-linked condition filtering
            _chromosome = getattr(variant, 'chromosome', None)
            _condition_name = info.get('condition', info.get('trait', info.get('drug', '')))
            if should_skip_sex_linked(rsid, _condition_name, info.get('gene'), _chromosome, ctx.inferred_sex):
                continue

            # Allele verification — confirm the user's genotype actually carries
            # the alternate (risk) allele from annotation data.  Both SNPs and
            # consumer-array indel codes (D/I) are now verified.
            if genotype and not is_indel_genotype(genotype):
                _, ann_alt = get_annotation_allele_parts(annotation_result)
                # FIX-02: skip when annotation data lacks allele information.
                # We cannot verify the user carries the risk allele vs reference,
                # so omit rather than risk a false positive.
                # (A prior info.get('risk_allele') fallback was removed — no
                # variant_mappings row has ever populated risk_allele, so it was
                # dead code; populating a real allele column is deferred — see U5.)
                if ann_alt is None:
                    logger.debug(
                        "rsid %s: no allele data for SNP verification — skipping", rsid
                    )
                    continue
                # ann_alt may be a comma-separated list for multi-allelic sites
                # (e.g. "A,T" for REF/A,T). Extract all single-base alts and
                # check whether the user carries ANY of them.
                _COMPLEMENT_MAP = str.maketrans('ACGT', 'TGCA')
                gt_upper = genotype.upper()
                alleles = set(gt_upper.replace('/', '').replace('|', ''))
                alleles_flipped = {a.translate(_COMPLEMENT_MAP) for a in alleles}
                ann_alts = [a.strip() for a in ann_alt.split(',') if a.strip()]
                snp_alts = [a for a in ann_alts if len(a) == 1]
                if snp_alts:
                    carries = any(a in alleles or a in alleles_flipped for a in snp_alts)
                    if not carries:
                        continue
                # If no single-base alt was extracted, fall through without allele
                # filtering (multi-base alt or structural variant — handled elsewhere).
            elif genotype and is_indel_genotype(genotype):
                # FIX-01: Verify consumer D/I indel codes against annotation allele
                # lengths.  D = shorter allele, I = longer allele.  indel_d_is_ref()
                # returns True when D maps to the reference (insertion variant), False
                # when D maps to the alternate (deletion variant), None when unknown.
                _ind_ref, _ind_alt = get_annotation_allele_parts(annotation_result)
                _d_is_ref = indel_d_is_ref(_ind_ref, _ind_alt)
                if _d_is_ref is not None:
                    # The risk (alternate) allele code
                    _risk_code = 'I' if _d_is_ref else 'D'
                    _user_codes = _parse_alleles(genotype) or []
                    if _risk_code not in _user_codes:
                        continue  # User carries only the reference indel allele
                elif genotype.strip().upper() in ('II', 'DD'):
                    # BUG-15: No allele data to determine insertion/deletion direction.
                    # For homozygous indel codes, we cannot confirm whether the user
                    # carries the risk (alternate) allele or the reference allele —
                    # either code can be hom-ref or hom-alt depending on the variant.
                    # Skip to avoid false positives (e.g. rs61749708 "II" = hom-ref).
                    # Heterozygous DI/ID is preserved since one allele is the insertion
                    # and one is the deletion, so the user plausibly carries the risk one.
                    logger.debug(
                        "rsid %s: homozygous indel %s with no allele-direction data — "
                        "skipping to prevent false positive (BUG-15)",
                        rsid, genotype,
                    )
                    continue
            key = info[dedup_field]
            if key not in seen:
                seen.add(key)
                # BUG-13: pass path_score so non-health generators can call
                # boost_if_pathogenic() before zygosity_adjust().
                _prof = ctx.variant_profiles.get(rsid)
                _path_score = (
                    _prof.pathogenicity_score if _prof
                    else (
                        annotation_result.annotation_data.get('pathogenicity_score')
                        if annotation_result and annotation_result.annotation_data else None
                    )
                )
                info_with_ref = {**info, '_ref_allele': effective_ref, '_pathogenicity_score': _path_score}
                # Skip "Unknown variant" entries unless the composite pathogenicity
                # score or ClinVar confirms meaningful evidence. Auto-categorization
                # produces these when no condition name could be resolved (BUG-06).
                _condition = info.get('condition', '')
                if _condition.lower() in ('unknown variant', 'unknown') and not (
                    isinstance(_path_score, dict) and _path_score.get('composite_score', 0) >= 0.60
                ):
                    logger.debug("rsid %s: skipping 'Unknown variant' mapping with no pathogenicity evidence", rsid)
                    continue
                # Skip generic "Gene Name variant" conditions that have no ClinVar
                # clinical significance. These are auto-generated fallback names
                # (e.g. "UBR4 variant") created when no real disease association
                # exists — usually caused by AlphaMissense coordinate mismatches
                # with MODIFIER/intergenic VEP consequences. Require either:
                #   a) non-empty clinical_significance from ClinVar, OR
                #   b) strong composite pathogenicity score (≥ 0.75)
                _is_generic_variant_condition = (
                    bool(re.search(r'\bvariant\s*$', _condition, re.IGNORECASE))
                    and _condition.lower() not in ('unknown variant',)
                    and not info.get('clinical_significance', '').strip()
                )
                if _is_generic_variant_condition and not (
                    isinstance(_path_score, dict) and _path_score.get('composite_score', 0) >= 0.75
                    and _path_score.get('evidence_count', 0) >= 2
                ):
                    logger.debug(
                        "rsid %s: skipping generic '%s' — no ClinVar significance and insufficient multi-source evidence",
                        rsid, _condition,
                    )
                    continue
                # Filter benign/likely_benign variants — applies to all panels.
                # Lifestyle panels with max_population_af already filter common
                # variants above, so this catches remaining benign-classified ones.
                if (settings.analysis.exclude_benign_from_panels
                        and isinstance(_path_score, dict)
                        and _path_score.get('classification') in _BENIGN_CLASSIFICATIONS):
                    continue
                # RC-7: When no scoring data exists and no ClinVar evidence,
                # skip for clinical panels (health/carrier/drug) to prevent
                # unscored variants from appearing as health risks.
                if (not skip_benign_filter
                        and max_population_af is not None and max_population_af <= 0.05
                        and not isinstance(_path_score, dict)):
                    if not info.get('clinical_significance', '').strip():
                        continue
                item = build_from_rsid(ctx.analysis_id, rsid, genotype or '', info_with_ref)
                if item:
                    items.append(item)

        # Gene-based matching from annotations — require a non-benign
        # consequence to avoid generating insights for synonymous or
        # intergenic variants that happen to sit in a known gene.
        gene, consequence, impact = extract_gene_and_consequence(
            annotation_result, ctx.rsid_gene_map
        )
        if gene and gene in gene_map:
            # P1-8: Skip gene matches where all annotation sources agree benign
            if is_clinvar_benign(annotation_result):
                continue

            # Filter: only moderate/high impact consequences qualify.
            # When consequence data is unavailable (gene came from ClinVar
            # rsid→gene map only), check ClinVar significance as a proxy
            # — a known pathogenic variant in a mapped gene should not be
            # silently dropped just because VEP data is missing.
            if impact and impact.lower() in ('high', 'moderate'):
                pass  # Qualifies
            elif consequence and consequence in (
                'missense_variant', 'stop_gained', 'frameshift_variant',
                'splice_acceptor_variant', 'splice_donor_variant',
                'stop_lost', 'start_lost', 'inframe_insertion',
                'inframe_deletion', 'protein_altering_variant',
            ):
                pass  # Qualifies by consequence type
            elif consequence is None and impact is None:
                # No VEP data — check ClinVar significance as fallback.
                # RC-6: Require rsid-specific ClinVar evidence, not just
                # gene-level. A pathogenic variant at position X doesn't
                # imply pathogenicity for an intron variant at position Y.
                _cv_qualifies = False
                if annotation_result and annotation_result.annotation_data:
                    cv_local = annotation_result.annotation_data.get('annotations', {}).get('clinvar_local', {})
                    if cv_local and cv_local.get('found'):
                        sigs = cv_local.get('clinical_significances', [])
                        sig_str = ' '.join(s.lower() for s in sigs)
                        has_path_sig = any(kw in sig_str for kw in ('pathogenic', 'drug_response'))
                        # Require the ClinVar record to match this specific rsid
                        cv_rsid = cv_local.get('rsid') or cv_local.get('rs_id') or ''
                        is_rsid_specific = str(cv_rsid) == str(rsid) or str(cv_rsid) == rsid.lstrip('rs')
                        if has_path_sig and is_rsid_specific:
                            _cv_qualifies = True
                if not _cv_qualifies:
                    continue
            else:
                continue  # Skip benign/low-impact variants

            info = gene_map[gene]
            key = info[dedup_field]
            if key not in seen:
                seen.add(key)
                # Pass genotype, ref allele, and pathogenicity score (BUG-13)
                _prof = ctx.variant_profiles.get(rsid)
                _path_score = (
                    _prof.pathogenicity_score if _prof
                    else (
                        annotation_result.annotation_data.get('pathogenicity_score')
                        if annotation_result and annotation_result.annotation_data else None
                    )
                )
                info_with_gt = {**info, '_ref_allele': effective_ref, '_genotype': genotype or '', '_pathogenicity_score': _path_score}
                if (settings.analysis.exclude_benign_from_panels
                        and isinstance(_path_score, dict)
                        and _path_score.get('classification') in _BENIGN_CLASSIFICATIONS):
                    continue
                item = build_from_gene(ctx.analysis_id, rsid, gene, consequence, info_with_gt)
                if item:
                    items.append(item)

    for item in items:
        validate_associated_variants(type(item).__name__, getattr(item, 'associated_variants', None))
        ctx.session.add(item)
    return len(items)


# ---------------------------------------------------------------------------
# Variant profile builder — runs ONCE before all generators
# ---------------------------------------------------------------------------

async def build_variant_profiles(
    variants,
    annotation_results: Dict[str, Any],
    rsid_gene_map: Dict[str, str],
) -> Dict[str, VariantProfile]:
    """Build pre-computed profiles for all variants in one pass.

    ARCH-06: Pathogenicity scores are computed HERE (lazily) rather than
    during Phase 2 annotation.  This means updated scoring logic always
    applies without re-annotating, and the annotation cache doesn't need
    to store pre-computed scores.
    """
    from ..scoring_engine import get_scoring_engine, ScoringEngine
    scorer = get_scoring_engine()
    profiles: Dict[str, VariantProfile] = {}

    gene_constraints = await _bulk_load_gene_constraints(rsid_gene_map)
    clinvar_gene_stats = await _bulk_load_clinvar_gene_stats(rsid_gene_map)

    for idx, variant in enumerate(variants):
        if idx > 0 and idx % 200 == 0:
            await asyncio.sleep(0)

        rsid = getattr(variant, 'rsid', None)
        if not rsid:
            continue

        genotype = get_user_genotype(variant)
        annotation_result = annotation_results.get(rsid)
        effective_ref = _get_effective_ref_allele(variant, annotation_result)

        gene, consequence, impact = extract_gene_and_consequence(
            annotation_result, rsid_gene_map
        )

        # Extract frequency — None means "no data available" (not 0%)
        raw_freq = extract_frequency(annotation_result)
        pop_freq = raw_freq if raw_freq > 0 else None

        # Pre-compute zygosity
        no_call = is_no_call_genotype(genotype)
        # Get full allele parts for indel D/I interpretation
        _, ann_alt = get_annotation_allele_parts(annotation_result)
        hom_ref = (not no_call and effective_ref is not None
                   and is_homozygous_reference(genotype, effective_ref, alt_allele=ann_alt))
        het = not no_call and not hom_ref and is_heterozygous(genotype)

        clinvar_benign = is_clinvar_benign(annotation_result)

        # Pathogenicity score — always compute fresh (ARCH-06).
        # Lazy scoring ensures updated scoring logic applies without re-annotating.
        annotations_dict: dict = {}
        if annotation_result and annotation_result.annotation_data:
            annotations_dict = annotation_result.annotation_data.get('annotations', {})
        if gene and gene in gene_constraints:
            annotations_dict = {**annotations_dict, 'gene_constraint': gene_constraints[gene]}
        if gene and gene in clinvar_gene_stats:
            annotations_dict = {**annotations_dict, 'clinvar_gene_stats': clinvar_gene_stats[gene]}
        pscore = scorer.score_variant(annotations_dict)
        composite = pscore.get('composite_score', 0.0)

        # Resolved clinical significance from ClinVar local
        clin_sig = None
        if annotation_result and annotation_result.annotation_data:
            cv_local = annotation_result.annotation_data.get(
                'annotations', {}
            ).get('clinvar_local', {})
            if cv_local and cv_local.get('found'):
                sigs = cv_local.get('clinical_significances', [])
                if sigs:
                    clin_sig = sigs[0].lower().replace('_', ' ')

        # is_benign: True when ClinVar unanimously says benign OR when the
        # composite pathogenicity score classifies as benign/likely_benign.
        # This covers variants with no ClinVar data that still score benign
        # from other evidence (e.g. VEP-only intron variants).
        score_benign = composite < ScoringEngine.BENIGN_THRESHOLD
        is_benign_flag = clinvar_benign or score_benign

        chromosome = getattr(variant, 'chromosome', None)

        profiles[rsid] = VariantProfile(
            rsid=rsid,
            genotype=genotype,
            effective_ref=effective_ref,
            gene=gene,
            consequence=consequence,
            impact=impact,
            chromosome=chromosome,
            population_frequency=pop_freq,
            clinical_significance=clin_sig,
            is_benign=is_benign_flag,
            is_hom_ref=hom_ref,
            is_het=het,
            is_no_call=no_call,
            composite_score=composite,
            pathogenicity_score=pscore,
            annotation_result=annotation_result,
            variant=variant,
        )

    logger.info(f"Built {len(profiles)} variant profiles")
    return profiles


async def _bulk_load_gene_constraints(rsid_gene_map: Dict[str, str]) -> Dict[str, dict]:
    """Pre-load gene constraint data for all genes in one query."""
    unique_genes = list(set(rsid_gene_map.values()))
    if not unique_genes:
        return {}
    try:
        from ...db.database import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT gene, pli, loeuf, mis_z, syn_z "
                    "FROM gnomad_gene_constraints WHERE gene = ANY(:genes)"
                ),
                {"genes": unique_genes},
            )
            return {
                row[0]: {"pli": row[1], "loeuf": row[2], "mis_z": row[3], "syn_z": row[4]}
                for row in result.all()
            }
    except Exception:
        return {}


async def _bulk_load_clinvar_gene_stats(rsid_gene_map: Dict[str, str]) -> Dict[str, dict]:
    """Pre-load ClinVar gene-level stats for all genes in one query."""
    unique_genes = list(set(rsid_gene_map.values()))
    if not unique_genes:
        return {}
    try:
        from ...db.database import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT gene, total_submissions, pathogenic_likely_pathogenic, "
                    "uncertain_significance, with_conflicts "
                    "FROM clinvar_gene_stats WHERE gene = ANY(:genes)"
                ),
                {"genes": unique_genes},
            )
            return {
                row[0]: {
                    "total_submissions": row[1],
                    "pathogenic_count": row[2],
                    "uncertain_count": row[3],
                    "conflict_count": row[4],
                }
                for row in result.all()
            }
    except Exception:
        return {}
