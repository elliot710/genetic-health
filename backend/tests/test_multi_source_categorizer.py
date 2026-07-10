import pytest
from backend.services import multi_source_categorizer as msc
from backend.services.multi_source_categorizer import (
    _conf_to_level,
    _category_aware_label,
    _category_extra_fields,
    extract_evidence,
    _is_severe,
    _risk_from_evidence,
    _compute_confidence,
    categorize_variant,
    SourceEvidence,
    CategorySuggestion,
    GENE_CATEGORY_MAP,
    _CONDITION_CATEGORY_KW,
    _SEVERE_EXCLUSION_KW,
)


@pytest.fixture(autouse=True)
def reset_global_maps():
    """Reset module-level maps before each test."""
    GENE_CATEGORY_MAP.clear()
    _CONDITION_CATEGORY_KW.clear()
    _SEVERE_EXCLUSION_KW.clear()
    yield
    GENE_CATEGORY_MAP.clear()
    _CONDITION_CATEGORY_KW.clear()
    _SEVERE_EXCLUSION_KW.clear()


class TestConfToLevel:
    def test_high(self):
        assert _conf_to_level(0.7) == "high"
        assert _conf_to_level(1.0) == "high"
        assert _conf_to_level(0.8) == "high"

    def test_moderate(self):
        assert _conf_to_level(0.4) == "moderate"
        assert _conf_to_level(0.6) == "moderate"

    def test_low(self):
        assert _conf_to_level(0.0) == "low"
        assert _conf_to_level(0.3) == "low"
        assert _conf_to_level(0.39) == "low"


class TestCategoryAwareLabel:
    def test_nutrition_nutrient(self):
        result = _category_aware_label("MTHFR", "nutrition", "nutrient")
        assert "MTHFR" in result
        assert "metabolism" in result

    def test_sports_category(self):
        result = _category_aware_label("ACTN3", "sports", "category")
        assert "ACTN3" in result
        assert "fitness" in result

    def test_wellness_metric(self):
        result = _category_aware_label("COMT", "wellness", "metric")
        assert "COMT" in result

    def test_cognitive_domain(self):
        result = _category_aware_label("BDNF", "cognitive", "domain")
        assert "BDNF" in result
        assert "cognition" in result

    def test_personality_trait(self):
        result = _category_aware_label("DRD4", "personality", "trait")
        assert "DRD4" in result

    def test_physical_trait(self):
        result = _category_aware_label("MC1R", "physical", "trait")
        assert "MC1R" in result

    def test_methylation_nutrient(self):
        result = _category_aware_label("MTHFR", "methylation", "nutrient")
        assert "MTHFR" in result
        assert "methylation" in result

    def test_detox_nutrient(self):
        result = _category_aware_label("CYP1A2", "detox", "nutrient")
        assert "CYP1A2" in result
        assert "detox" in result

    def test_drug_drug(self):
        result = _category_aware_label("CYP2D6", "drug", "drug")
        assert "CYP2D6" in result

    def test_unknown_category_fallback(self):
        result = _category_aware_label("GENE1", "unknown_category", "some_field")
        assert "GENE1" in result
        assert "variant" in result

    def test_unknown_field_in_known_category(self):
        result = _category_aware_label("GENE1", "health", "some_field")
        assert "GENE1" in result
        assert "variant" in result


class TestCategoryExtraFields:
    def test_drug_returns_drugs_list(self):
        data = {"drug": "Warfarin", "condition": "Anticoagulation"}
        result = _category_extra_fields("drug", data, 0.7)
        assert "drugs" in result
        assert isinstance(result["drugs"], list)

    def test_physical_returns_result_and_description(self):
        data = {"gene": "MC1R", "trait": "Hair color"}
        result = _category_extra_fields("physical", data, 0.6)
        assert "result" in result
        assert "description" in result

    def test_nutrition_returns_sensitivity(self):
        data = {"nutrient": "Folate", "gene": "MTHFR"}
        result = _category_extra_fields("nutrition", data, 0.5)
        assert "sensitivity" in result
        assert "recommendations" in result

    def test_sports_returns_advantage(self):
        data = {"category": "Endurance", "gene": "ACTN3"}
        result = _category_extra_fields("sports", data, 0.6)
        assert "advantage" in result
        assert "recommendations" in result

    def test_cognitive_returns_score(self):
        data = {"domain": "Memory"}
        result = _category_extra_fields("cognitive", data, 0.7)
        assert "score" in result
        assert "percentile" in result

    def test_personality_returns_tendency(self):
        data = {"trait": "Risk-taking"}
        result = _category_extra_fields("personality", data, 0.5)
        assert "tendency" in result
        assert "insights" in result

    def test_wellness_returns_predisposition(self):
        data = {"metric": "Stress response"}
        result = _category_extra_fields("wellness", data, 0.6)
        assert "predisposition" in result
        assert "recommendations" in result

    def test_methylation_returns_capacity(self):
        data = {"gene": "MTHFR"}
        result = _category_extra_fields("methylation", data, 0.6)
        assert "capacity" in result

    def test_detox_returns_phase(self):
        data = {"gene": "CYP1A2"}
        result = _category_extra_fields("detox", data, 0.6)
        assert "phase" in result
        assert "capacity" in result

    def test_health_returns_empty(self):
        data = {}
        result = _category_extra_fields("health", data, 0.7)
        assert result == {}

    def test_confidence_affects_level(self):
        data = {"nutrient": "Folate", "gene": "MTHFR"}
        low_conf = _category_extra_fields("nutrition", data, 0.2)
        high_conf = _category_extra_fields("nutrition", data, 0.9)
        assert low_conf["sensitivity"] == "low"
        assert high_conf["sensitivity"] == "high"


class TestExtractEvidence:
    def test_empty_annotations(self):
        result = extract_evidence({})
        assert result == []

    def test_clinvar_local_found(self):
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Pathogenic"],
                "conditions": ["Breast cancer"],
                "genes": ["BRCA1"],
                "review_statuses": ["criteria provided"],
            }
        }
        evidence = extract_evidence(annotations)
        assert len(evidence) == 1
        assert evidence[0].source_name == "clinvar_local"
        assert evidence[0].gene == "BRCA1"
        assert evidence[0].pathogenicity_score == 0.9

    def test_clinvar_local_not_found_ignored(self):
        annotations = {"clinvar_local": {"found": False}}
        assert extract_evidence(annotations) == []

    def test_clinvar_api_found(self):
        annotations = {
            "clinvar": {
                "found": True,
                "entries": [
                    {"clinical_significance": ["Pathogenic"], "conditions": ["Diabetes"]}
                ]
            }
        }
        evidence = extract_evidence(annotations)
        cv = next((e for e in evidence if e.source_name == "clinvar_api"), None)
        assert cv is not None

    def test_ensembl_vep_found(self):
        annotations = {
            "ensembl": {
                "found": True,
                "data": [{
                    "most_severe_consequence": "missense_variant",
                    "transcript_consequences": [
                        {"gene_symbol": "BRCA2", "sift_score": 0.02, "polyphen_score": 0.95}
                    ]
                }]
            }
        }
        evidence = extract_evidence(annotations)
        vep = next((e for e in evidence if e.source_name == "ensembl_vep"), None)
        assert vep is not None
        assert vep.gene == "BRCA2"
        assert vep.consequence == "missense_variant"

    def test_ensembl_vep_polyphen_preferred(self):
        annotations = {
            "ensembl": {
                "found": True,
                "data": [{
                    "most_severe_consequence": "missense_variant",
                    "transcript_consequences": [
                        {"gene_symbol": "TP53", "sift_score": 0.1, "polyphen_score": 0.95}
                    ]
                }]
            }
        }
        evidence = extract_evidence(annotations)
        vep = next((e for e in evidence if e.source_name == "ensembl_vep"), None)
        assert vep is not None
        assert vep.pathogenicity_score == pytest.approx(0.95)

    def test_alpha_missense_found(self):
        annotations = {
            "alpha_missense": {
                "found": True,
                "am_pathogenicity": 0.85
            }
        }
        evidence = extract_evidence(annotations)
        am = next((e for e in evidence if e.source_name == "alpha_missense"), None)
        assert am is not None
        assert am.pathogenicity_score == pytest.approx(0.85)

    def test_gnomad_found(self):
        annotations = {
            "gnomad_local": {
                "found": True,
                "af": 0.0001,
                "gene": "BRCA1",
                "cadd": {"phred": 25}
            }
        }
        evidence = extract_evidence(annotations)
        gnomad = next((e for e in evidence if e.source_name == "gnomad"), None)
        assert gnomad is not None
        assert gnomad.allele_frequency == pytest.approx(0.0001)
        assert gnomad.pathogenicity_score == pytest.approx(0.7)

    def test_gnomad_cadd_thresholds(self):
        annotations = {
            "gnomad_local": {"found": True, "cadd": {"phred": 31}},
        }
        evidence = extract_evidence(annotations)
        gnomad = next((e for e in evidence if e.source_name == "gnomad"), None)
        assert gnomad.pathogenicity_score == pytest.approx(0.9)

    def test_snpedia_found(self):
        annotations = {"snpedia": {"found": True}}
        evidence = extract_evidence(annotations)
        assert any(e.source_name == "snpedia" for e in evidence)

    def test_thousand_genomes_found(self):
        annotations = {"thousand_genomes": {"found": True, "global_af": 0.05}}
        evidence = extract_evidence(annotations)
        tg = next((e for e in evidence if e.source_name == "1000genomes"), None)
        assert tg is not None
        assert tg.allele_frequency == pytest.approx(0.05)

    def test_gnomad_tx_found(self):
        annotations = {"gnomad_tx_data": {"found": True}}
        evidence = extract_evidence(annotations)
        assert any(e.source_name == "gnomad_tx" for e in evidence)

    def test_clinvar_local_pathogenicity_likely(self):
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Likely_pathogenic"],
                "conditions": [],
                "genes": [],
                "review_statuses": [],
            }
        }
        evidence = extract_evidence(annotations)
        assert evidence[0].pathogenicity_score == pytest.approx(0.75)

    def test_clinvar_local_benign(self):
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Benign"],
                "conditions": [],
                "genes": [],
                "review_statuses": [],
            }
        }
        evidence = extract_evidence(annotations)
        assert evidence[0].pathogenicity_score == pytest.approx(0.1)

    def test_clinvar_local_risk_factor(self):
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Risk factor"],
                "conditions": [],
                "genes": [],
                "review_statuses": [],
            }
        }
        evidence = extract_evidence(annotations)
        assert evidence[0].pathogenicity_score == pytest.approx(0.5)

    def test_noise_conditions_filtered(self):
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Pathogenic"],
                "conditions": ["not provided", "not specified", "Breast cancer"],
                "genes": [],
                "review_statuses": [],
            }
        }
        evidence = extract_evidence(annotations)
        assert "not provided" not in evidence[0].conditions
        assert "Breast cancer" in evidence[0].conditions


class TestIsSevere:
    def test_not_severe_without_keywords(self):
        _SEVERE_EXCLUSION_KW.clear()
        assert _is_severe("mild condition") is False

    def test_severe_with_keyword(self):
        _SEVERE_EXCLUSION_KW.add("cancer")
        assert _is_severe("Breast cancer") is True

    def test_case_insensitive_match(self):
        _SEVERE_EXCLUSION_KW.add("cancer")
        assert _is_severe("BREAST CANCER") is True

    def test_partial_match_in_longer_string(self):
        _SEVERE_EXCLUSION_KW.add("cardiomyopathy")
        assert _is_severe("Hypertrophic cardiomyopathy") is True

    def test_no_match(self):
        _SEVERE_EXCLUSION_KW.add("cancer")
        assert _is_severe("Folate metabolism") is False


class TestRiskFromEvidence:
    def test_no_pathogenicity_scores(self):
        evidence = [SourceEvidence("clinvar_local")]
        assert _risk_from_evidence(evidence) == pytest.approx(1.1)

    def test_high_pathogenicity(self):
        evidence = [SourceEvidence("clinvar_local", pathogenicity_score=0.90)]
        risk = _risk_from_evidence(evidence)
        assert risk >= 2.0

    def test_moderately_high_pathogenicity(self):
        evidence = [SourceEvidence("clinvar_local", pathogenicity_score=0.75)]
        risk = _risk_from_evidence(evidence)
        assert 1.5 <= risk < 2.0

    def test_moderate_pathogenicity(self):
        evidence = [SourceEvidence("clinvar_local", pathogenicity_score=0.55)]
        risk = _risk_from_evidence(evidence)
        assert 1.2 <= risk < 1.5

    def test_low_pathogenicity(self):
        evidence = [SourceEvidence("clinvar_local", pathogenicity_score=0.35)]
        risk = _risk_from_evidence(evidence)
        assert 1.1 <= risk < 1.2

    def test_very_low_pathogenicity(self):
        evidence = [SourceEvidence("clinvar_local", pathogenicity_score=0.1)]
        risk = _risk_from_evidence(evidence)
        assert risk == pytest.approx(1.0)

    def test_multiple_confirming_sources_bonus(self):
        evidence = [
            SourceEvidence("clinvar_local", pathogenicity_score=0.9),
            SourceEvidence("ensembl_vep", pathogenicity_score=0.8),
            SourceEvidence("alpha_missense", pathogenicity_score=0.85),
        ]
        risk = _risk_from_evidence(evidence)
        # bonus for 3 confirming sources
        assert risk > 2.0

    def test_capped_at_3(self):
        evidence = [
            SourceEvidence("s1", pathogenicity_score=0.99),
            SourceEvidence("s2", pathogenicity_score=0.99),
            SourceEvidence("s3", pathogenicity_score=0.99),
            SourceEvidence("s4", pathogenicity_score=0.99),
        ]
        risk = _risk_from_evidence(evidence)
        assert risk <= 3.0


class TestComputeConfidence:
    def test_empty_returns_zero(self):
        assert _compute_confidence([], "health") == 0.0

    def test_single_source(self):
        evidence = [SourceEvidence("clinvar_local")]
        conf = _compute_confidence(evidence, "health")
        assert 0.0 < conf <= 0.75

    def test_more_sources_higher_confidence(self):
        one = _compute_confidence([SourceEvidence("s1")], "health")
        three = _compute_confidence(
            [SourceEvidence("s1"), SourceEvidence("s2"), SourceEvidence("s3")],
            "health"
        )
        assert three > one

    def test_agreement_bonus(self):
        # Two sources both high → agreement bonus
        evidence_agree = [
            SourceEvidence("s1", pathogenicity_score=0.8),
            SourceEvidence("s2", pathogenicity_score=0.9),
        ]
        evidence_no_scores = [
            SourceEvidence("s1"),
            SourceEvidence("s2"),
        ]
        conf_agree = _compute_confidence(evidence_agree, "health")
        conf_no = _compute_confidence(evidence_no_scores, "health")
        assert conf_agree >= conf_no

    def test_gene_category_match_bonus(self):
        GENE_CATEGORY_MAP["BRCA1"] = ["health"]
        evidence = [SourceEvidence("clinvar_local", gene="BRCA1")]
        conf = _compute_confidence(evidence, "health")
        without_map = _compute_confidence([SourceEvidence("clinvar_local", gene="UNKNOWN")], "health")
        assert conf > without_map

    def test_capped_at_one(self):
        evidence = [SourceEvidence(f"s{i}", pathogenicity_score=0.9) for i in range(10)]
        conf = _compute_confidence(evidence, "health")
        assert conf <= 1.0


class TestCategorizeVariant:
    def test_no_evidence_returns_empty(self):
        result = categorize_variant("rs12345", {})
        assert result == []

    def test_pathogenic_sig_gives_health(self):
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Pathogenic"],
                "conditions": ["Breast cancer"],
                "genes": ["BRCA1"],
                "review_statuses": [],
            }
        }
        suggestions = categorize_variant("rs12345", annotations)
        categories = {s.category for s in suggestions}
        assert "health" in categories

    def test_drug_response_sig_gives_drug(self):
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["drug response"],
                "conditions": ["Warfarin sensitivity"],
                "genes": ["CYP2C9"],
                "review_statuses": [],
            }
        }
        suggestions = categorize_variant("rs12345", annotations)
        categories = {s.category for s in suggestions}
        assert "drug" in categories

    def test_gene_hint_routes_correctly(self):
        GENE_CATEGORY_MAP["ACTN3"] = ["sports"]
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Benign"],
                "conditions": [],
                "genes": [],
                "review_statuses": [],
            }
        }
        suggestions = categorize_variant("rs1815739", annotations, gene_hint="ACTN3")
        categories = {s.category for s in suggestions}
        assert "sports" in categories

    def test_severe_condition_excluded_from_lifestyle(self):
        _SEVERE_EXCLUSION_KW.add("cancer")
        GENE_CATEGORY_MAP["BRCA1"] = ["sports"]
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Pathogenic"],
                "conditions": ["Breast cancer"],
                "genes": ["BRCA1"],
                "review_statuses": [],
            }
        }
        suggestions = categorize_variant("rs12345", annotations)
        # Sports is lifestyle, should be excluded for severe condition
        categories = {s.category for s in suggestions}
        assert "sports" not in categories

    def test_benign_sig_excluded_from_health(self):
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Benign"],
                "conditions": ["Polymorphism"],
                "genes": ["SOME_GENE"],
                "review_statuses": [],
            }
        }
        suggestions = categorize_variant("rs12345", annotations)
        categories = {s.category for s in suggestions}
        assert "health" not in categories
        assert "rare" not in categories

    def test_sorted_by_confidence_descending(self):
        GENE_CATEGORY_MAP["BRCA1"] = ["health", "carrier"]
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Pathogenic"],
                "conditions": ["Breast cancer"],
                "genes": ["BRCA1"],
                "review_statuses": [],
            }
        }
        suggestions = categorize_variant("rs12345", annotations, gene_hint="BRCA1")
        if len(suggestions) >= 2:
            for i in range(len(suggestions) - 1):
                assert suggestions[i].confidence >= suggestions[i + 1].confidence

    def test_condition_hints_used(self):
        condition_hints = {
            "gene_conditions": {"TP53": ["Li-Fraumeni syndrome"]},
            "gene_descriptions": {},
        }
        annotations = {
            "ensembl": {
                "found": True,
                "data": [{
                    "most_severe_consequence": "stop_gained",
                    "transcript_consequences": [{"gene_symbol": "TP53"}]
                }]
            }
        }
        suggestions = categorize_variant("rs12345", annotations, gene_hint="TP53",
                                         condition_hints=condition_hints)
        if suggestions:
            found_cond = any("Li-Fraumeni" in s.condition for s in suggestions)
            assert found_cond

    def test_rare_category_for_ultra_rare_variant(self):
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Pathogenic"],
                "conditions": ["Rare disease"],
                "genes": ["GENE1"],
                "review_statuses": [],
            },
            "gnomad_local": {
                "found": True,
                "af": 0.00005,
                "consequence": "missense_variant",
                "impact": "MODERATE",
            }
        }
        suggestions = categorize_variant("rs12345", annotations)
        categories = {s.category for s in suggestions}
        assert "rare" in categories

    def test_result_has_required_fields(self):
        annotations = {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Pathogenic"],
                "conditions": ["Some disease"],
                "genes": ["GENE1"],
                "review_statuses": [],
            }
        }
        suggestions = categorize_variant("rs12345", annotations)
        assert len(suggestions) > 0
        s = suggestions[0]
        assert hasattr(s, "category")
        assert hasattr(s, "confidence")
        assert hasattr(s, "sources")
        assert hasattr(s, "condition")
        assert hasattr(s, "gene")
        assert hasattr(s, "risk_multiplier")
        assert hasattr(s, "data")
