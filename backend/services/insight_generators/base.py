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


def is_homozygous_reference(genotype: Optional[str]) -> bool:
    """Return True when the genotype is homozygous (both alleles identical).

    For a rare pathogenic SNV (freq < 1%), being homozygous almost
    certainly means the user carries two copies of the **reference**
    allele, not the pathogenic alternate (probability < 0.0001%).
    """
    if not genotype:
        return False
    gt = genotype.strip().upper()
    # Handle different genotype formats
    if '/' in gt:
        alleles = gt.split('/')
    elif '|' in gt:
        alleles = gt.split('|')
    elif len(gt) == 2:
        alleles = [gt[0], gt[1]]
    elif len(gt) == 1:
        # Hemizygous (e.g. X chromosome in males) — single allele,
        # treat as "not heterozygous" but don't skip since it could
        # be the alternate allele.
        return False
    else:
        return False
    return len(alleles) == 2 and alleles[0] == alleles[1]


# ---------------------------------------------------------------------------
# Scoring / recommendation helpers
# ---------------------------------------------------------------------------

def assess_risk_level(genotype: str, risk_multiplier: float) -> str:
    if not genotype:
        return 'unknown'
    if risk_multiplier >= 2.0:
        return 'high'
    elif risk_multiplier >= 1.2:
        return 'moderate'
    elif risk_multiplier <= 0.8:
        return 'low'
    return 'average'


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
                item = build_from_rsid(ctx.analysis_id, rsid, genotype, info)
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
