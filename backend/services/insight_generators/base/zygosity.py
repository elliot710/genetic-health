"""
Zygosity-aware risk/severity adjustment and scoring/recommendation helpers.
"""
import logging
from typing import Dict, List, Optional

from .alleles import (
    is_no_call_genotype, is_homozygous_reference, is_heterozygous, is_indel_genotype,
)

logger = logging.getLogger(__name__)


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
