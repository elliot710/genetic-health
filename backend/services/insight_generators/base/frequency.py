"""
Annotation extraction helpers for gene/consequence and population frequency
(pure functions, no DB access).
"""
from typing import Dict, Optional


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


def resolve_population_frequency(annotations: Dict) -> Optional[float]:
    """Resolve the population allele frequency from a merged annotations dict
    (the ``annotation_data['annotations']`` shape), trying sources in order:

    1. Ensembl VEP colocated_variants gnomAD frequencies
    2. gnomAD local allele frequency (af)
    3. 1000 Genomes global allele frequency

    Returns ``None`` when no source carries a frequency — distinct from a
    genuine ``0.0``. Callers that need the rarity signal (matching gate, scorer,
    risk assessment) must treat ``None`` as *unknown*, not *ultra-rare*.
    """
    if not annotations:
        return None

    try:
        # 1. Ensembl VEP
        ensembl_data = annotations.get('ensembl', {})
        data_list = ensembl_data.get('data', [])
        if data_list:
            entry = data_list[0]
            freqs = entry.get('colocated_variants', [{}])[0].get('frequencies', {})
            if freqs:
                first_allele = next(iter(freqs.values()), {})
                val = first_allele.get('gnomade', first_allele.get('gnomad'))
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

    return None


def extract_frequency(annotation_result) -> float:
    """Population frequency for an annotation_result, as a float (0.0 when
    unknown). Thin wrapper over :func:`resolve_population_frequency` that
    preserves the legacy float contract for existing callers."""
    if not annotation_result or not annotation_result.annotation_data:
        return 0.0
    annotations = annotation_result.annotation_data.get('annotations', {})
    resolved = resolve_population_frequency(annotations)
    return resolved if resolved is not None else 0.0
