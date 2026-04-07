"""
Auto-discovery service for generating variant mappings
from external lookup results. Entries require admin approval before going live.
"""
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db.models import PendingDiscovery, VariantMapping

# Maps clinical significance keywords → panel categories
CLINICAL_PANEL_MAP = {
    'pathogenic': 'health',
    'likely_pathogenic': 'health',
    'risk_factor': 'wellness',
    'drug_response': 'drug',
    'protective': 'health',
}

# Consequence types that suggest a panel assignment
CONSEQUENCE_PANEL_MAP = {
    'missense_variant': 'health',
    'frameshift_variant': 'health',
    'stop_gained': 'health',
    'splice_donor_variant': 'health',
    'splice_acceptor_variant': 'health',
}


async def process_lookup_discoveries(
    session: AsyncSession,
    rsid: str,
    response_data: Dict[str, Any],
    user_id: Optional[int] = None
) -> int:
    """
    Analyze lookup results and create pending discoveries for admin review.
    Skips if the rsid already exists in live tables or pending queue.
    Returns the number of new discoveries created.
    """
    if not response_data or not response_data.get('found'):
        return 0

    basic_info = response_data.get('basic_info', {})
    gene = basic_info.get('gene_symbol')
    consequence = basic_info.get('most_severe_consequence', '').replace(' ', '_')
    clinical_sigs = response_data.get('clinical_significance', [])
    pharmacogenomics = response_data.get('pharmacogenomics', {})
    population_data = response_data.get('population_data', {})

    created = 0

    # Generate variant mapping suggestions
    mappings = _determine_variant_mappings(rsid, gene, consequence, clinical_sigs, pharmacogenomics, population_data)

    for mapping_cat, mapping_info in mappings.items():
        map_type = mapping_info['map_type']
        key = mapping_info['key']

        # Check if already live
        existing_mapping = await session.execute(
            select(VariantMapping.id).where(
                VariantMapping.category == mapping_cat,
                VariantMapping.map_type == map_type,
                VariantMapping.key == key,
            )
        )
        if existing_mapping.scalar_one_or_none() is not None:
            continue

        # Check if already pending — use panel_id=mapping_cat for uniqueness
        existing_pending = await session.execute(
            select(PendingDiscovery).where(
                PendingDiscovery.discovery_type == 'variant_mapping',
                PendingDiscovery.rsid == rsid,
                PendingDiscovery.panel_id == mapping_cat,
            )
        )
        pending = existing_pending.scalar_one_or_none()
        if pending:
            if pending.status == 'pending':
                pending.lookup_count = (pending.lookup_count or 1) + 1
            continue

        discovery = PendingDiscovery(
            discovery_type='variant_mapping',
            rsid=rsid,
            gene=gene,
            panel_id=mapping_cat,  # Used as part of unique index
            map_type=map_type,
            mapping_category=mapping_cat,
            mapping_data=mapping_info['data'],
            description=mapping_info.get('description', ''),
            source_data={
                'basic_info': basic_info,
                'clinical_significance': clinical_sigs,
                'consequence': consequence,
            },
            status='pending',
            discovered_by=user_id,
            lookup_count=1,
        )
        session.add(discovery)
        created += 1

    if created > 0:
        await session.flush()

    return created


def _determine_variant_mappings(
    rsid: str,
    gene: str | None,
    consequence: str,
    clinical_sigs: list,
    pharmacogenomics: dict,
    population_data: dict | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Determine which variant mappings should be suggested."""
    mappings: Dict[str, Dict[str, Any]] = {}
    sig_lower = [s.lower().replace(' ', '_') for s in clinical_sigs]

    # RC-3: Skip common variants (AF > 1%) unless ClinVar pathogenic
    allele_freq = _extract_allele_frequency(population_data)
    has_pathogenic = any('pathogenic' in s for s in sig_lower)
    if allele_freq is not None and allele_freq > 0.01 and not has_pathogenic:
        return mappings

    # Health risk mapping for pathogenic/risk variants
    # RC-4: risk_factor goes to wellness, not health
    has_health_signal = any(
        kw in sig for sig in sig_lower
        for kw in ('pathogenic', 'likely_pathogenic')
    )
    has_risk_factor = any('risk_factor' in sig for sig in sig_lower)
    if has_health_signal or consequence in CONSEQUENCE_PANEL_MAP:
        condition = _infer_condition(clinical_sigs, gene)
        mappings['health'] = {
            'map_type': 'rsid',
            'key': rsid,
            'data': {
                'condition': condition or f"{gene or 'Unknown'} variant",
                'risk_multiplier': 1.2 if 'pathogenic' in str(sig_lower) else 1.1,
            },
            'description': f"Health risk: {condition}" if condition else f"Health variant in {gene or 'unknown gene'}",
        }

    # RC-4: Route risk_factor to wellness panel instead of health
    if has_risk_factor and 'health' not in mappings:
        condition = _infer_condition(clinical_sigs, gene)
        mappings['wellness'] = {
            'map_type': 'rsid',
            'key': rsid,
            'data': {
                'metric': condition or f"{gene or 'Unknown'} risk factor",
                'predisposition': 'moderate',
                'score': 0.5,
                'recommendations': [f'Discuss {gene or "this variant"} with healthcare provider'],
            },
            'description': f"Wellness risk factor: {condition or gene}",
        }

    # Drug response mapping
    has_drug_signal = any('drug_response' in sig for sig in sig_lower)
    if has_drug_signal or pharmacogenomics.get('found'):
        gene_label = gene or 'Unknown'
        drugs = []
        pharm_data = pharmacogenomics.get('data', {})
        if isinstance(pharm_data, dict):
            drugs = pharm_data.get('relatedChemicals', [])
            if isinstance(drugs, list):
                drugs = [d.get('name', d) if isinstance(d, dict) else str(d) for d in drugs[:5]]
        mappings['drug'] = {
            'map_type': 'rsid',
            'key': rsid,
            'data': {
                'gene': gene_label,
                'drugs': drugs or ['unknown'],
            },
            'description': f"Drug response: {gene_label}",
        }

    return mappings


def _extract_allele_frequency(population_data: dict | None) -> float | None:
    """Extract global allele frequency from population data."""
    if not population_data or not isinstance(population_data, dict):
        return None
    af = population_data.get('global_af') or population_data.get('af')
    if af is not None:
        try:
            return float(af)
        except (ValueError, TypeError):
            pass
    frequencies = population_data.get('frequencies', {})
    if isinstance(frequencies, dict):
        for key in ('global', 'gnomad', 'gnomade', '1000genomes'):
            val = frequencies.get(key)
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
    return None


def _infer_condition(clinical_sigs: list, gene: str | None) -> str | None:
    """Try to infer a condition name from clinical significance and gene."""
    for sig in clinical_sigs:
        lower = sig.lower()
        if 'pathogenic' in lower:
            return f"{gene} associated condition" if gene else None
        if 'risk' in lower:
            return f"{gene} risk factor" if gene else None
    return None
