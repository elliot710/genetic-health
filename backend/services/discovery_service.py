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
    'risk_factor': 'health',
    'drug_response': 'drug_responses',
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

# Gene-based category inference for health panel sub-categories
GENE_CATEGORY_MAP = {
    # Cardiovascular
    'APOE': 'cardiovascular', 'LDLR': 'cardiovascular', 'PCSK9': 'cardiovascular',
    'MTHFR': 'cardiovascular', 'F5': 'cardiovascular', 'F2': 'cardiovascular',
    'ACE': 'cardiovascular', 'AGT': 'cardiovascular', 'NOS3': 'cardiovascular',
    # Metabolic
    'TCF7L2': 'metabolic', 'PPARG': 'metabolic', 'FTO': 'metabolic',
    'MC4R': 'metabolic', 'SLC30A8': 'metabolic', 'GCKR': 'metabolic',
    # Neurological
    'PARK2': 'neurological', 'LRRK2': 'neurological', 'SNCA': 'neurological',
    'APP': 'neurological', 'PSEN1': 'neurological', 'PSEN2': 'neurological',
    'MAPT': 'neurological', 'GBA': 'neurological',
    # Cancer
    'BRCA1': 'cancer', 'BRCA2': 'cancer', 'TP53': 'cancer',
    'APC': 'cancer', 'MLH1': 'cancer', 'MSH2': 'cancer',
    'RB1': 'cancer', 'PTEN': 'cancer', 'VHL': 'cancer',
    # Pharmacogenomics / drug metabolism
    'CYP2D6': 'pharmacogenomic', 'CYP2C19': 'pharmacogenomic', 'CYP2C9': 'pharmacogenomic',
    'CYP1A2': 'pharmacogenomic', 'CYP3A4': 'pharmacogenomic', 'CYP3A5': 'pharmacogenomic',
    'NAT2': 'pharmacogenomic', 'DPYD': 'pharmacogenomic', 'TPMT': 'pharmacogenomic',
    'UGT1A1': 'pharmacogenomic', 'SLCO1B1': 'pharmacogenomic', 'VKORC1': 'pharmacogenomic',
    'ABCB1': 'pharmacogenomic',
    # Immune
    'HLA-A': 'immune', 'HLA-B': 'immune', 'HLA-C': 'immune',
    'IL6': 'immune', 'TNF': 'immune', 'TNFRSF14': 'immune',
    # Methylation
    'COMT': 'methylation_enzymes', 'MTR': 'methylation_enzymes',
    'MTRR': 'methylation_enzymes', 'CBS': 'transsulfuration',
    'BHMT': 'methylation_enzymes', 'MAO-A': 'neurotransmitter',
    # Detox
    'GSTP1': 'phase2', 'GSTM1': 'phase2', 'GSTT1': 'phase2',
    'SOD2': 'antioxidant', 'CAT': 'antioxidant', 'GPX1': 'antioxidant',
    'NQO1': 'phase2',
}

# Consequence-based sub-category inference
CONSEQUENCE_CATEGORY_MAP = {
    'missense_variant': 'metabolic',
    'frameshift_variant': 'metabolic',
    'stop_gained': 'metabolic',
    'splice_donor_variant': 'metabolic',
    'splice_acceptor_variant': 'metabolic',
    'intron_variant': 'regulatory',
    'upstream_gene_variant': 'regulatory',
    'downstream_gene_variant': 'regulatory',
    'synonymous_variant': 'regulatory',
}

# Drug response sub-categories based on drug class keywords
DRUG_CATEGORY_MAP = {
    'warfarin': 'anticoagulants', 'heparin': 'anticoagulants', 'rivaroxaban': 'anticoagulants',
    'clopidogrel': 'antiplatelet', 'aspirin': 'antiplatelet',
    'statin': 'statins', 'atorvastatin': 'statins', 'simvastatin': 'statins', 'rosuvastatin': 'statins',
    'omeprazole': 'proton_pump_inhibitors', 'pantoprazole': 'proton_pump_inhibitors',
    'codeine': 'opioids', 'tramadol': 'opioids', 'morphine': 'opioids',
    'tamoxifen': 'oncology', 'fluorouracil': 'oncology', 'irinotecan': 'oncology',
    'metformin': 'antidiabetics',
    'phenytoin': 'anticonvulsants', 'carbamazepine': 'anticonvulsants',
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
    mappings = _determine_variant_mappings(rsid, gene, consequence, clinical_sigs, pharmacogenomics)

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


def _infer_subcategory(gene: str | None, consequence: str, clinical_sigs: list, pharmacogenomics: dict, panel_id: str) -> str:
    """Infer a proper sub-category for the given panel based on gene, consequence, and clinical data."""
    # 1. Gene-based lookup (most specific)
    if gene and gene.upper() in GENE_CATEGORY_MAP:
        gene_cat = GENE_CATEGORY_MAP[gene.upper()]
        # For drug_responses panel, remap pharmacogenomic genes
        if panel_id == 'drug_responses':
            return _infer_drug_subcategory(pharmacogenomics, gene)
        return gene_cat

    # 2. For drug_responses, infer from drug data
    if panel_id == 'drug_responses':
        return _infer_drug_subcategory(pharmacogenomics, gene)

    # 3. Consequence-based fallback for health panel
    if consequence and consequence in CONSEQUENCE_CATEGORY_MAP:
        return CONSEQUENCE_CATEGORY_MAP[consequence]

    # 4. Generic defaults per panel
    defaults = {
        'health': 'metabolic',
        'drug_responses': 'pharmacogenomic',
        'rare_mutations': 'metabolic',
        'uncommon_mutations': 'metabolic',
        'wellness': 'metabolic',
    }
    return defaults.get(panel_id, 'general')


def _infer_drug_subcategory(pharmacogenomics: dict, gene: str | None) -> str:
    """Infer drug response sub-category from pharmacogenomics data."""
    pharm_data = pharmacogenomics.get('data', {})
    if isinstance(pharm_data, dict):
        chemicals = pharm_data.get('relatedChemicals', [])
        if isinstance(chemicals, list):
            for chem in chemicals:
                name = (chem.get('name', '') if isinstance(chem, dict) else str(chem)).lower()
                for keyword, category in DRUG_CATEGORY_MAP.items():
                    if keyword in name:
                        return category
    # Known pharmacogene families
    if gene:
        g = gene.upper()
        if g.startswith('CYP'):
            return 'pharmacogenomic'
        if g == 'VKORC1':
            return 'anticoagulants'
        if g == 'SLCO1B1':
            return 'statins'
    return 'pharmacogenomic'


def _determine_variant_mappings(
    rsid: str,
    gene: str | None,
    consequence: str,
    clinical_sigs: list,
    pharmacogenomics: dict,
) -> Dict[str, Dict[str, Any]]:
    """Determine which variant mappings should be suggested."""
    mappings: Dict[str, Dict[str, Any]] = {}
    sig_lower = [s.lower().replace(' ', '_') for s in clinical_sigs]

    # Health risk mapping for pathogenic/risk variants
    has_health_signal = any(
        kw in sig for sig in sig_lower
        for kw in ('pathogenic', 'risk_factor', 'likely_pathogenic')
    )
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


def _infer_condition(clinical_sigs: list, gene: str | None) -> str | None:
    """Try to infer a condition name from clinical significance and gene."""
    for sig in clinical_sigs:
        lower = sig.lower()
        if 'pathogenic' in lower:
            return f"{gene} associated condition" if gene else None
        if 'risk' in lower:
            return f"{gene} risk factor" if gene else None
    return None
