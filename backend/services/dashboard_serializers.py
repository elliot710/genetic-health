from typing import Dict, Any, Tuple


def _dedup_by(items: list, key: str) -> list:
    seen: set = set()
    result = []
    for item in items:
        val = item.get(key)
        if val not in seen:
            seen.add(val)
            result.append(item)
    return result


def _clean_trait_name(raw: str) -> str:
    if not raw:
        return "Unknown"
    if '|' not in raw and ';' not in raw:
        return raw
    parts = raw.replace(';', '|').split('|')
    skip = {'not provided', 'not specified', 'see cases', 'not applicable'}
    for part in parts:
        cleaned = part.strip()
        if cleaned and cleaned.lower() not in skip:
            if cleaned.isupper():
                cleaned = cleaned.title()
            return cleaned
    return parts[0].strip().title() if parts else raw


def _to_list(val) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val:
        return [val]
    return []


def serialize_health_risks(rows) -> list:
    return _dedup_by([
        {"condition": _clean_trait_name(r.condition), "risk_level": r.risk_level,
         "risk_score": r.risk_score, "associated_variants": r.associated_variants,
         "recommendations": _to_list(r.recommendations), "gene": r.gene,
         "review_status": r.review_status,
         "pathogenicity_classification": r.pathogenicity_classification}
        for r in rows
    ], "condition")


def serialize_drug_responses(rows) -> list:
    return _dedup_by([
        {"gene": r.gene, "drug": r.drug, "response_type": r.response_type,
         "recommendations": _to_list(r.recommendations), "variants_involved": r.variants_involved}
        for r in rows
    ], "drug")


def serialize_ancestry(rows) -> list:
    return _dedup_by([
        {"population": r.population, "percentage": r.percentage, "confidence": r.confidence,
         "geographic_origin": r.geographic_origin, "composition": r.composition,
         "maternal_haplogroup": r.maternal_haplogroup, "paternal_haplogroup": r.paternal_haplogroup,
         "neanderthal_variants": r.neanderthal_variants}
        for r in rows
    ], "population")


def serialize_sports(rows) -> list:
    return _dedup_by([
        {"category": r.performance_category, "genetic_advantage": r.genetic_advantage,
         "sport_recommendations": _to_list(r.sport_recommendations),
         "training_advice": r.training_advice, "associated_variants": r.associated_variants or []}
        for r in rows
    ], "category")


def serialize_nutrition(rows) -> list:
    return _dedup_by([
        {"nutrient": r.nutrient, "metabolism_type": r.metabolism_type,
         "dietary_recommendations": _to_list(r.dietary_recommendations),
         "sensitivity_level": r.sensitivity_level, "associated_variants": r.associated_variants or []}
        for r in rows
    ], "nutrient")


def serialize_carrier_status(rows) -> list:
    return _dedup_by([
        {"condition": _clean_trait_name(r.condition), "carrier_status": r.carrier_status,
         "inheritance_pattern": r.inheritance_pattern, "associated_variants": r.associated_variants or [],
         "genetic_counseling_recommended": r.genetic_counseling_recommended, "gene": r.gene or ""}
        for r in rows
    ], "condition")


def serialize_methylation(rows) -> list:
    return _dedup_by([
        {"gene": r.gene, "variant": r.variant, "methylation_capacity": r.methylation_capacity,
         "supplement_recommendations": _to_list(r.supplement_recommendations),
         "associated_variants": r.associated_variants}
        for r in rows
    ], "gene")


def serialize_detox(rows) -> list:
    return _dedup_by([
        {"detox_phase": r.detox_phase, "gene": r.gene, "detox_capacity": r.detox_capacity,
         "toxin_sensitivity": r.toxin_sensitivity,
         "support_recommendations": _to_list(r.support_recommendations),
         "associated_variants": r.associated_variants}
        for r in rows
    ], "gene")


def serialize_rare_mutations(rows) -> list:
    return _dedup_by([
        {"gene": r.gene, "mutation_type": r.mutation_type,
         "mutation_name": _clean_trait_name(r.mutation_name),
         "clinical_significance": r.clinical_significance,
         "disease_association": _clean_trait_name(r.disease_association) if r.disease_association else r.disease_association,
         "penetrance": r.penetrance, "population_frequency": r.population_frequency,
         "associated_variants": r.associated_variants,
         "clinical_actions": _to_list(r.clinical_actions),
         "monitoring_recommendations": _to_list(r.monitoring_recommendations)}
        for r in rows
    ], "mutation_name")


def serialize_wellness(rows) -> Tuple[dict, list]:
    metabolic = {"metrics": _dedup_by([
        {"metric_name": r.metric_name, "genetic_predisposition": r.genetic_predisposition,
         "optimization_score": r.optimization_score,
         "lifestyle_recommendations": r.lifestyle_recommendations}
        for r in rows
    ], "metric_name")} if rows else {}
    wellness_traits = _dedup_by([
        {"trait": _clean_trait_name(r.metric_name), "category": "Wellness",
         "value": r.genetic_predisposition, "gene": "Multiple",
         "confidence": r.optimization_score or "Medium",
         "name": _clean_trait_name(r.metric_name), "result": r.genetic_predisposition,
         "marker": "Multiple genes", "associated_variants": r.associated_variants or [],
         "recommendations": _to_list(r.lifestyle_recommendations)}
        for r in rows
    ], "trait") if rows else []
    return metabolic, wellness_traits


def serialize_physical_traits(rows) -> list:
    return _dedup_by([
        {"trait_name": _clean_trait_name(r.trait_name),
         "trait_category": _clean_trait_name(r.trait_category),
         "genetic_result": r.genetic_result, "confidence": r.confidence,
         "associated_variants": r.associated_variants, "description": r.description,
         "category": _clean_trait_name(r.trait_category)}
        for r in rows
    ], "trait_name") if rows else []


def serialize_cognitive(rows) -> list:
    return _dedup_by([
        {"cognitive_ability": _clean_trait_name(r.cognitive_domain),
         "trait_name": _clean_trait_name(r.cognitive_domain),
         "genetic_advantage": r.genetic_score, "genetic_result": r.genetic_score,
         "percentile": r.percentile, "associated_variants": r.associated_variants,
         "description": '; '.join(r.enhancement_suggestions) if isinstance(r.enhancement_suggestions, list) else (r.enhancement_suggestions or ''),
         "enhancement_suggestions": r.enhancement_suggestions if isinstance(r.enhancement_suggestions, list) else ([r.enhancement_suggestions] if r.enhancement_suggestions else [])}
        for r in rows
    ], "trait_name") if rows else []


def serialize_personality(rows) -> list:
    return _dedup_by([
        {"trait": _clean_trait_name(r.trait_name), "name": _clean_trait_name(r.trait_name),
         "score": 70 if r.genetic_tendency == 'moderate' else (85 if r.genetic_tendency == 'high' else 55),
         "confidence": r.confidence_level,
         "gene": r.associated_variants[0] if r.associated_variants else "Multiple markers",
         "marker": r.associated_variants[0] if r.associated_variants else "Multiple markers",
         "associated_variants": r.associated_variants or [],
         "description": (_to_list(r.behavioral_insights) or ["Genetic analysis based"])[0],
         "summary": (_to_list(r.behavioral_insights) or ["Genetic analysis based"])[0],
         "characteristics": _to_list(r.behavioral_insights) or ["Trait-based behavior"]}
        for r in rows
    ], "trait") if rows else []


def serialize_uncommon_mutations(rows) -> list:
    return _dedup_by([
        {"rsid": r.associated_variants[0] if r.associated_variants else r.mutation_name,
         "gene": r.gene, "effect": _clean_trait_name(r.trait_association or r.mutation_name),
         "population_frequency": r.population_frequency or 0, "effect_size": r.effect_size or "small",
         "research_status": r.research_status or "emerging",
         "clinical_relevance": r.clinical_significance or "low",
         "literature_count": 0, "mutation_name": r.mutation_name, "mutation_type": r.mutation_type}
        for r in rows
    ], "mutation_name") if rows else []


def serialize_insight_rows(rows: Dict[str, Any]) -> Dict[str, Any]:
    metabolic, wellness_traits = serialize_wellness(rows['wellness'])
    return {
        "health_risks": serialize_health_risks(rows['health']),
        "drug_responses": serialize_drug_responses(rows['drug']),
        "ancestry_results": serialize_ancestry(rows['ancestry']),
        "sports_performance": serialize_sports(rows['sports']),
        "nutrition_traits": serialize_nutrition(rows['nutrition']),
        "carrier_status": serialize_carrier_status(rows['carrier']),
        "methylation_profiles": serialize_methylation(rows['methylation']),
        "detoxification_profiles": serialize_detox(rows['detox']),
        "rare_mutations": serialize_rare_mutations(rows['rare']),
        "metabolic": metabolic,
        "wellness_traits": wellness_traits,
        "physical_traits": serialize_physical_traits(rows['physical']),
        "intelligence": serialize_cognitive(rows['cognitive']),
        "personality_traits": serialize_personality(rows['personality']),
        "uncommon_mutations": serialize_uncommon_mutations(rows['uncommon']),
    }
