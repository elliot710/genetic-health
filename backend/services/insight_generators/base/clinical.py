"""
ClinVar significance aggregation, sex-linked condition filtering, GWAS
trait classification, and ClinGen gene-disease validity checks.
"""
from typing import Dict, List, Optional, Any

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
