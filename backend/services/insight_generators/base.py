"""
Shared context, helpers, and generic map-driven generator used by all
insight generator modules.
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import AnalysisVariant


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
                    if gene:
                        consequence = tc.get('consequence_terms', [None])[0] if tc.get('consequence_terms') else None
                        impact = tc.get('impact')
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
    """Extract population frequency from annotation data."""
    if not annotation_result or not annotation_result.annotation_data:
        return 0.0

    try:
        ensembl_data = annotation_result.annotation_data.get('annotations', {}).get('ensembl', {})
        data_list = ensembl_data.get('data', [])
        if not data_list:
            return 0.0

        entry = data_list[0]
        freqs = entry.get('colocated_variants', [{}])[0].get('frequencies', {})
        if freqs:
            first_allele = next(iter(freqs.values()), {})
            return first_allele.get('gnomade', first_allele.get('gnomad', 0.0))
        return 0.0
    except (KeyError, IndexError, TypeError, StopIteration):
        return 0.0


def get_ref_allele(variant) -> Optional[str]:
    """Extract the reference allele from the variant's marker."""
    marker = getattr(variant, 'marker', None)
    if marker:
        ref = getattr(marker, 'ref_allele', None)
        if ref and ref not in ('N', '-', '.', ''):
            return ref
    return None


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


def _parse_alleles(genotype: Optional[str]):
    """Split a genotype string into a list of alleles, or return None.
    
    For hemizygous genotypes (single allele, e.g. X chromosome in males),
    returns a single-element list so callers can handle it.
    """
    if not genotype:
        return None
    gt = genotype.strip().upper()
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


def is_homozygous_reference(genotype: Optional[str], ref_allele: Optional[str] = None) -> bool:
    """Return True when the user carries only the reference allele.

    Handles diploid (2 alleles) and hemizygous (1 allele, e.g. X chromosome in males).
    When *ref_allele* is provided we check explicitly.  Without it we
    fall back to heuristics.
    """
    alleles = _parse_alleles(genotype)
    if alleles is None:
        return False
    if ref_allele:
        ref = ref_allele.strip().upper()
        return all(a == ref for a in alleles)
    # Fallback: treat any homozygous as "reference" (inaccurate for homo-alt)
    # For hemizygous, we can't tell without ref_allele so return False
    if len(alleles) == 1:
        return False
    return alleles[0] == alleles[1]


def is_heterozygous(genotype: Optional[str]) -> bool:
    """Return True when the genotype has two different alleles.
    Hemizygous genotypes (1 allele) are never heterozygous."""
    alleles = _parse_alleles(genotype)
    if alleles is None or len(alleles) < 2:
        return False
    return alleles[0] != alleles[1]


# Severity ladder used by zygosity_adjust — from mildest to most severe
_SEVERITY_LADDER = ['low', 'average', 'moderate', 'high', 'very_high']
_SEVERITY_IDX = {v: i for i, v in enumerate(_SEVERITY_LADDER)}


def zygosity_adjust(level: str, genotype: Optional[str], *, ref_allele: Optional[str] = None, steps: int = 1) -> str:
    """Shift a severity/level string up or down based on zygosity.

    - Homozygous reference (both alleles == ref): de-escalate by *steps*
    - Heterozygous (one alternate allele): keep as-is (the mapping baseline)
    - Homozygous alternate (both alleles != ref): escalate by *steps*

    When *ref_allele* is supplied the classification is exact.
    Without it the function uses a heuristic (any homozygous → reference).
    """
    normalised = level.strip().lower().replace(' ', '_')
    idx = _SEVERITY_IDX.get(normalised)
    if idx is None:
        return level  # not on the ladder — nothing to shift

    if is_homozygous_reference(genotype, ref_allele) or not genotype:
        new_idx = max(0, idx - steps)
    elif is_heterozygous(genotype):
        new_idx = idx  # baseline — no change
    else:
        # Homozygous non-reference
        new_idx = min(len(_SEVERITY_LADDER) - 1, idx + steps)

    result = _SEVERITY_LADDER[new_idx]
    # Preserve original casing style (Title Case if original was)
    if level[0].isupper():
        result = result.replace('_', ' ').title()
    return result


# ---------------------------------------------------------------------------
# Scoring / recommendation helpers
# ---------------------------------------------------------------------------

def assess_risk_level(genotype: str, risk_multiplier: float, ref_allele: Optional[str] = None) -> str:
    """Assess risk level considering both the risk multiplier and zygosity."""
    if not genotype:
        return 'unknown'
    # Base level from multiplier
    if risk_multiplier >= 2.0:
        base = 'high'
    elif risk_multiplier >= 1.2:
        base = 'moderate'
    elif risk_multiplier <= 0.8:
        base = 'low'
    else:
        base = 'average'
    # Adjust for zygosity
    return zygosity_adjust(base, genotype, ref_allele=ref_allele)


def assess_drug_response(genotype: str, gene: str) -> str:
    if not genotype:
        return 'normal'
    if gene == 'CYP2C9' and ('*2' in genotype or '*3' in genotype):
        return 'poor'
    elif gene == 'CYP2C19' and '*2' in genotype:
        return 'poor'
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
) -> int:
    """
    Generic loop shared by most category generators.

    Args:
        rsid_map / gene_map: lookup dicts from variant_registry.
        dedup_field: key inside the info dict used to avoid duplicates.
        build_from_rsid(analysis_id, rsid, genotype, info) -> model | None
        build_from_gene(analysis_id, rsid, gene, consequence, info) -> model | None
    """
    items = []
    seen: set = set()

    for variant in ctx.variants:
        rsid = getattr(variant, 'rsid', None)
        if not rsid:
            continue

        # rsid-based matching
        if rsid in rsid_map:
            info = rsid_map[rsid]
            key = info[dedup_field]
            if key not in seen:
                seen.add(key)
                genotype = getattr(variant, 'genotype', '') or ''
                ref_allele = getattr(getattr(variant, 'marker', None), 'ref_allele', None)
                info_with_ref = {**info, '_ref_allele': ref_allele}
                item = build_from_rsid(ctx.analysis_id, rsid, genotype, info_with_ref)
                if item:
                    items.append(item)

        # Gene-based matching from annotations
        annotation_result = ctx.annotation_results.get(rsid)
        gene, consequence, impact = extract_gene_and_consequence(
            annotation_result, ctx.rsid_gene_map
        )
        if gene and gene in gene_map:
            info = gene_map[gene]
            key = info[dedup_field]
            if key not in seen:
                seen.add(key)
                item = build_from_gene(ctx.analysis_id, rsid, gene, consequence, info)
                if item:
                    items.append(item)

    for item in items:
        ctx.session.add(item)
    return len(items)
