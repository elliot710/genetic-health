import pytest
from backend.services.scoring_engine import (
    ScoringEngine, ScoringResult, SourceEvidence, get_scoring_engine, _SOURCE_WEIGHTS
)


@pytest.fixture
def engine():
    return ScoringEngine()


class TestClinvarSignificanceToScore:
    def test_pathogenic(self):
        score, label = ScoringEngine._clinvar_significance_to_score("Pathogenic")
        assert score == 0.95
        assert label == "Pathogenic"

    def test_likely_pathogenic_underscore(self):
        # 'pathogenic' appears as substring in 'likely_pathogenic' → matches first at 0.95
        score, label = ScoringEngine._clinvar_significance_to_score("Likely_pathogenic")
        assert score == 0.95

    def test_likely_pathogenic_space(self):
        # Same substring matching: 'pathogenic' in 'likely pathogenic'
        score, label = ScoringEngine._clinvar_significance_to_score("Likely pathogenic")
        assert score == 0.95

    def test_uncertain_significance(self):
        score, label = ScoringEngine._clinvar_significance_to_score("Uncertain significance")
        assert score == 0.50

    def test_uncertain_significance_underscore(self):
        score, label = ScoringEngine._clinvar_significance_to_score("uncertain_significance")
        assert score == 0.50

    def test_likely_benign(self):
        score, label = ScoringEngine._clinvar_significance_to_score("Likely benign")
        assert score == 0.20

    def test_benign(self):
        score, label = ScoringEngine._clinvar_significance_to_score("Benign")
        assert score == 0.05
        assert label == "Benign"

    def test_risk_factor(self):
        score, label = ScoringEngine._clinvar_significance_to_score("Risk factor")
        assert score == 0.60

    def test_protective(self):
        score, label = ScoringEngine._clinvar_significance_to_score("Protective")
        assert score == 0.05

    def test_drug_response(self):
        score, label = ScoringEngine._clinvar_significance_to_score("drug response")
        assert score == 0.50

    def test_association(self):
        score, label = ScoringEngine._clinvar_significance_to_score("Association")
        assert score == 0.55

    def test_affects(self):
        score, label = ScoringEngine._clinvar_significance_to_score("Affects")
        assert score == 0.50

    def test_conflicting_interpretations(self):
        score, label = ScoringEngine._clinvar_significance_to_score("Conflicting interpretations")
        assert score == 0.50

    def test_unknown_sig(self):
        score, label = ScoringEngine._clinvar_significance_to_score("Some_new_classification")
        assert score == 0.50
        assert "Unknown" in label

    def test_compound_takes_max(self):
        score, label = ScoringEngine._clinvar_significance_to_score("Pathogenic/Likely_pathogenic")
        assert score == 0.95

    def test_case_insensitive(self):
        score, _ = ScoringEngine._clinvar_significance_to_score("PATHOGENIC")
        assert score == 0.95


class TestCaddToScore:
    def test_high_phred_above_30(self):
        assert ScoringEngine._cadd_to_score(35) == 0.95
        assert ScoringEngine._cadd_to_score(30) == 0.95

    def test_phred_25(self):
        score = ScoringEngine._cadd_to_score(25)
        assert 0.75 < score < 0.95

    def test_phred_20(self):
        score = ScoringEngine._cadd_to_score(20)
        assert score == pytest.approx(0.75)

    def test_phred_17(self):
        score = ScoringEngine._cadd_to_score(17)
        assert 0.55 < score < 0.75

    def test_phred_15(self):
        score = ScoringEngine._cadd_to_score(15)
        assert score == pytest.approx(0.55)

    def test_phred_12(self):
        score = ScoringEngine._cadd_to_score(12)
        assert 0.35 < score < 0.55

    def test_phred_10(self):
        score = ScoringEngine._cadd_to_score(10)
        assert score == pytest.approx(0.35)

    def test_phred_7(self):
        score = ScoringEngine._cadd_to_score(7)
        assert 0.15 < score < 0.35

    def test_phred_5(self):
        score = ScoringEngine._cadd_to_score(5)
        assert score == pytest.approx(0.15)

    def test_phred_2(self):
        score = ScoringEngine._cadd_to_score(2)
        assert 0.0 < score < 0.15

    def test_phred_0(self):
        score = ScoringEngine._cadd_to_score(0)
        assert score == 0.0


class TestAfToScore:
    def test_zero_af_ambiguous(self):
        assert ScoringEngine._af_to_score(0.0) == 0.50

    def test_negative_af(self):
        assert ScoringEngine._af_to_score(-0.001) == 0.50

    def test_ultra_rare(self):
        assert ScoringEngine._af_to_score(0.00005) == 0.85

    def test_very_rare(self):
        assert ScoringEngine._af_to_score(0.0005) == 0.70

    def test_rare(self):
        assert ScoringEngine._af_to_score(0.005) == 0.50

    def test_low_frequency(self):
        assert ScoringEngine._af_to_score(0.02) == 0.25

    def test_common(self):
        assert ScoringEngine._af_to_score(0.10) == 0.10
        assert ScoringEngine._af_to_score(0.50) == 0.10

    def test_boundary_0001(self):
        assert ScoringEngine._af_to_score(0.0001) == 0.70

    def test_boundary_001(self):
        assert ScoringEngine._af_to_score(0.001) == 0.50

    def test_boundary_01(self):
        assert ScoringEngine._af_to_score(0.01) == 0.25

    def test_boundary_05(self):
        assert ScoringEngine._af_to_score(0.05) == 0.10


class TestAfLabel:
    def test_zero(self):
        label = ScoringEngine._af_label(0)
        assert "Not observed" in label

    def test_ultra_rare(self):
        label = ScoringEngine._af_label(0.00005)
        assert "Ultra-rare" in label

    def test_very_rare(self):
        label = ScoringEngine._af_label(0.0005)
        assert "Very rare" in label

    def test_rare(self):
        label = ScoringEngine._af_label(0.005)
        assert "Rare" in label

    def test_low_frequency(self):
        label = ScoringEngine._af_label(0.02)
        assert "Low frequency" in label

    def test_common(self):
        label = ScoringEngine._af_label(0.10)
        assert "Common" in label


class TestConsequenceToScore:
    def test_stop_gained_high(self):
        assert ScoringEngine._consequence_to_score("stop_gained") == 0.85

    def test_frameshift_high(self):
        assert ScoringEngine._consequence_to_score("frameshift_variant") == 0.85

    def test_splice_acceptor_high(self):
        assert ScoringEngine._consequence_to_score("splice_acceptor_variant") == 0.85

    def test_splice_donor_high(self):
        assert ScoringEngine._consequence_to_score("splice_donor_variant") == 0.85

    def test_transcript_ablation_high(self):
        assert ScoringEngine._consequence_to_score("transcript_ablation") == 0.85

    def test_stop_lost_high(self):
        assert ScoringEngine._consequence_to_score("stop_lost") == 0.85

    def test_start_lost_high(self):
        assert ScoringEngine._consequence_to_score("start_lost") == 0.85

    def test_missense_moderate(self):
        assert ScoringEngine._consequence_to_score("missense_variant") == 0.55

    def test_inframe_insertion_moderate(self):
        assert ScoringEngine._consequence_to_score("inframe_insertion") == 0.55

    def test_inframe_deletion_moderate(self):
        assert ScoringEngine._consequence_to_score("inframe_deletion") == 0.55

    def test_protein_altering_moderate(self):
        assert ScoringEngine._consequence_to_score("protein_altering_variant") == 0.55

    def test_synonymous_low(self):
        assert ScoringEngine._consequence_to_score("synonymous_variant") == 0.25

    def test_splice_region_low(self):
        assert ScoringEngine._consequence_to_score("splice_region_variant") == 0.25

    def test_intron_low(self):
        assert ScoringEngine._consequence_to_score("intron_variant") == 0.10

    def test_upstream_low(self):
        assert ScoringEngine._consequence_to_score("upstream_gene_variant") == 0.10

    def test_downstream_low(self):
        assert ScoringEngine._consequence_to_score("downstream_gene_variant") == 0.10

    def test_intergenic_low(self):
        assert ScoringEngine._consequence_to_score("intergenic_variant") == 0.10

    def test_unknown_returns_none(self):
        assert ScoringEngine._consequence_to_score("totally_unknown_consequence") is None

    def test_spaces_handled(self):
        assert ScoringEngine._consequence_to_score("stop gained") == 0.85


class TestExtractClinvarSignificance:
    def test_direct_string(self):
        data = {"found": True, "clinical_significance": "Pathogenic"}
        assert ScoringEngine._extract_clinvar_significance(data) == "Pathogenic"

    def test_direct_list(self):
        data = {"found": True, "clinical_significance": ["Likely pathogenic", "Pathogenic"]}
        assert ScoringEngine._extract_clinvar_significance(data) == "Likely pathogenic"

    def test_nested_data_list(self):
        data = {
            "found": True,
            "data": [{"clinical_significance": "Benign"}]
        }
        assert ScoringEngine._extract_clinvar_significance(data) == "Benign"

    def test_nested_data_dict(self):
        data = {
            "found": True,
            "data": {"clinical_significance": "Uncertain significance"}
        }
        assert ScoringEngine._extract_clinvar_significance(data) == "Uncertain significance"

    def test_entries_array(self):
        data = {
            "found": True,
            "entries": [{"clinical_significance": ["Risk factor"]}]
        }
        assert ScoringEngine._extract_clinvar_significance(data) == "Risk factor"

    def test_empty_data(self):
        data = {"found": True}
        assert ScoringEngine._extract_clinvar_significance(data) == ""

    def test_nested_data_list_with_list_sig(self):
        data = {
            "found": True,
            "data": [{"clinical_significance": ["Pathogenic"]}]
        }
        assert ScoringEngine._extract_clinvar_significance(data) == "Pathogenic"


class TestClassify:
    def test_pathogenic(self, engine):
        assert engine._classify(0.90) == "pathogenic"
        assert engine._classify(0.80) == "pathogenic"

    def test_likely_pathogenic(self, engine):
        assert engine._classify(0.70) == "likely_pathogenic"
        assert engine._classify(0.60) == "likely_pathogenic"

    def test_uncertain(self, engine):
        assert engine._classify(0.50) == "uncertain"
        assert engine._classify(0.30) == "uncertain"

    def test_likely_benign(self, engine):
        assert engine._classify(0.20) == "likely_benign"
        assert engine._classify(0.15) == "likely_benign"

    def test_benign(self, engine):
        assert engine._classify(0.10) == "benign"
        assert engine._classify(0.00) == "benign"


class TestComputeConfidence:
    def test_high_confidence(self, engine):
        assert engine._compute_confidence(4, 0.80, 0.0) == "high"

    def test_moderate_confidence(self, engine):
        result = engine._compute_confidence(2, 0.40, 0.0)
        assert result in ("moderate", "high")

    def test_low_confidence(self, engine):
        result = engine._compute_confidence(1, 0.15, 0.0)
        assert result in ("low", "moderate", "none")

    def test_none_confidence_zero(self, engine):
        assert engine._compute_confidence(0, 0.0, 0.0) == "none"

    def test_penalty_reduces_confidence(self, engine):
        without_penalty = engine._compute_confidence(4, 0.80, 0.0)
        with_penalty = engine._compute_confidence(4, 0.80, 0.5)
        confidence_map = {"none": 0, "low": 1, "moderate": 2, "high": 3}
        assert confidence_map[with_penalty] <= confidence_map[without_penalty]


class TestDetectConflicts:
    def test_no_conflicts(self, engine):
        evidences = [
            SourceEvidence("clinvar", 0.90, 0.30, "Pathogenic"),
            SourceEvidence("cadd", 0.85, 0.15, "High CADD"),
        ]
        assert engine._detect_conflicts(evidences) == []

    def test_conflict_benign_vs_pathogenic(self, engine):
        evidences = [
            SourceEvidence("clinvar", 0.90, 0.30, "Pathogenic"),
            SourceEvidence("gnomad_af", 0.10, 0.10, "Common"),
        ]
        conflicts = engine._detect_conflicts(evidences)
        assert len(conflicts) >= 1

    def test_clinvar_vs_cadd_conflict(self, engine):
        evidences = [
            SourceEvidence("clinvar", 0.95, 0.30, "Pathogenic"),
            SourceEvidence("cadd", 0.20, 0.15, "Low CADD"),
        ]
        conflicts = engine._detect_conflicts(evidences)
        assert len(conflicts) >= 1

    def test_all_benign_no_conflict(self, engine):
        evidences = [
            SourceEvidence("clinvar", 0.05, 0.30, "Benign"),
            SourceEvidence("cadd", 0.10, 0.15, "Low CADD"),
        ]
        assert engine._detect_conflicts(evidences) == []


class TestScoreClinvar:
    def test_found_pathogenic(self, engine):
        data = {"found": True, "clinical_significance": "Pathogenic"}
        ev = engine._score_clinvar(data)
        assert ev is not None
        assert ev.score == 0.95
        assert ev.source == "clinvar"

    def test_not_found_returns_none(self, engine):
        assert engine._score_clinvar({"found": False}) is None

    def test_none_data_returns_none(self, engine):
        assert engine._score_clinvar(None) is None

    def test_missing_sig_returns_none(self, engine):
        assert engine._score_clinvar({"found": True}) is None

    def test_benign(self, engine):
        data = {"found": True, "clinical_significance": "Benign"}
        ev = engine._score_clinvar(data)
        assert ev is not None
        assert ev.score == 0.05


class TestScoreClinvarLocal:
    def test_found_likely_pathogenic(self, engine):
        data = {"found": True, "clinical_significance": "Likely pathogenic"}
        ev = engine._score_clinvar_local(data)
        assert ev is not None
        assert ev.source == "clinvar_local"
        assert ev.score == 0.95  # 'pathogenic' matches as substring first

    def test_not_found(self, engine):
        assert engine._score_clinvar_local({"found": False}) is None


class TestScoreGnomad:
    def test_cadd_evidence(self, engine):
        data = {
            "found": True,
            "cadd": {"phred": 25, "interpretation": "Highly deleterious"},
        }
        results = engine._score_gnomad(data)
        cadd_ev = next((e for e in results if e.source == "cadd"), None)
        assert cadd_ev is not None
        assert 0.75 < cadd_ev.score < 0.95

    def test_sift_evidence(self, engine):
        data = {
            "found": True,
            "predictions": {"sift": {"score": 0.01, "category": "deleterious"}},
        }
        results = engine._score_gnomad(data)
        sift_ev = next((e for e in results if e.source == "sift"), None)
        assert sift_ev is not None
        assert sift_ev.score == pytest.approx(0.99)

    def test_polyphen_evidence(self, engine):
        data = {
            "found": True,
            "predictions": {"polyphen": {"score": 0.95, "category": "probably_damaging"}},
        }
        results = engine._score_gnomad(data)
        pp_ev = next((e for e in results if e.source == "polyphen"), None)
        assert pp_ev is not None
        assert pp_ev.score == pytest.approx(0.95)

    def test_conservation_evidence(self, engine):
        data = {
            "found": True,
            "conservation": {"vertebrate": 7.0},
        }
        results = engine._score_gnomad(data)
        cons_ev = next((e for e in results if e.source == "conservation"), None)
        assert cons_ev is not None
        assert cons_ev.score == pytest.approx(1.0)

    def test_conservation_negative(self, engine):
        data = {
            "found": True,
            "conservation": {"vertebrate": -5.0},
        }
        results = engine._score_gnomad(data)
        cons_ev = next((e for e in results if e.source == "conservation"), None)
        assert cons_ev is not None
        assert cons_ev.score == 0.0

    def test_splice_ai_evidence(self, engine):
        data = {
            "found": True,
            "splice_ai": {"max_score": 0.8},
        }
        results = engine._score_gnomad(data)
        splice_ev = next((e for e in results if e.source == "splice_ai"), None)
        assert splice_ev is not None
        assert splice_ev.score == 0.8

    def test_splice_ai_zero_excluded(self, engine):
        data = {
            "found": True,
            "splice_ai": {"max_score": 0.0},
        }
        results = engine._score_gnomad(data)
        assert not any(e.source == "splice_ai" for e in results)

    def test_af_evidence(self, engine):
        data = {
            "found": True,
            "af": 0.00005,
        }
        results = engine._score_gnomad(data)
        af_ev = next((e for e in results if e.source == "gnomad_af"), None)
        assert af_ev is not None
        assert af_ev.score == 0.85

    def test_cadd_only_no_af_evidence(self, engine):
        data = {"found": True, "cadd": {"raw": 3.2, "phred": 25.0, "interpretation": "High"}}
        results = engine._score_gnomad(data)
        assert not any(e.source == "gnomad_af" for e in results)

    def test_empty_data_no_evidence(self, engine):
        data = {"found": True}
        assert engine._score_gnomad(data) == []

    def test_all_sources_combined(self, engine):
        data = {
            "found": True,
            "cadd": {"phred": 30},
            "predictions": {
                "sift": {"score": 0.02},
                "polyphen": {"score": 0.90},
            },
            "conservation": {"vertebrate": 5.0},
            "splice_ai": {"max_score": 0.6},
            "af": 0.0001,
        }
        results = engine._score_gnomad(data)
        sources = {e.source for e in results}
        assert "cadd" in sources
        assert "sift" in sources
        assert "polyphen" in sources
        assert "conservation" in sources
        assert "splice_ai" in sources
        assert "gnomad_af" in sources


class TestScoreAlphaMissense:
    def test_am_pathogenicity_key(self, engine):
        ev = engine._score_alpha_missense({"am_pathogenicity": 0.85, "am_class": "pathogenic"})
        assert ev is not None
        assert ev.score == 0.85
        assert ev.source == "alpha_missense"

    def test_score_key(self, engine):
        ev = engine._score_alpha_missense({"score": 0.20})
        assert ev is not None
        assert ev.score == 0.20

    def test_pathogenicity_score_key(self, engine):
        ev = engine._score_alpha_missense({"pathogenicity_score": 0.50})
        assert ev is not None
        assert ev.score == 0.50

    def test_none_data(self, engine):
        assert engine._score_alpha_missense(None) is None

    def test_empty_data(self, engine):
        assert engine._score_alpha_missense({}) is None

    def test_invalid_score(self, engine):
        assert engine._score_alpha_missense({"am_pathogenicity": "not_a_number"}) is None


class TestScoreEnsembl:
    def test_most_severe_consequence(self, engine):
        data = {
            "found": True,
            "data": [{"most_severe_consequence": "stop_gained"}]
        }
        ev = engine._score_ensembl(data)
        assert ev is not None
        assert ev.score == 0.85

    def test_transcript_consequences_fallback(self, engine):
        data = {
            "found": True,
            "data": [{
                "transcript_consequences": [
                    {"consequence_terms": ["missense_variant"]}
                ]
            }]
        }
        ev = engine._score_ensembl(data)
        assert ev is not None
        assert ev.score == 0.55

    def test_none_data(self, engine):
        assert engine._score_ensembl(None) is None

    def test_not_found(self, engine):
        assert engine._score_ensembl({"found": False}) is None

    def test_empty_data_list(self, engine):
        assert engine._score_ensembl({"found": True, "data": []}) is None

    def test_unknown_consequence_returns_none(self, engine):
        data = {
            "found": True,
            "data": [{"most_severe_consequence": "completely_unknown_consequence"}]
        }
        assert engine._score_ensembl(data) is None


class TestAggregate:
    def test_empty_evidences(self, engine):
        result = engine._aggregate([])
        assert isinstance(result, ScoringResult)
        assert result.evidence_count == 0

    def test_single_clinvar_pathogenic(self, engine):
        ev = SourceEvidence("clinvar", 0.95, _SOURCE_WEIGHTS["clinvar"], "Pathogenic")
        result = engine._aggregate([ev])
        assert result.composite_score > 0.0
        assert result.evidence_count == 1

    def test_clinvar_authoritative_override(self, engine):
        evidences = [
            SourceEvidence("clinvar", 0.95, _SOURCE_WEIGHTS["clinvar"], "Pathogenic"),
            SourceEvidence("cadd", 0.80, _SOURCE_WEIGHTS["cadd"], "High CADD"),
        ]
        result = engine._aggregate(evidences)
        assert result.composite_score == 0.95
        assert result.classification == "pathogenic"

    def test_clinvar_override_blocked_by_benign_conflict(self, engine):
        evidences = [
            SourceEvidence("clinvar", 0.95, _SOURCE_WEIGHTS["clinvar"], "Pathogenic"),
            SourceEvidence("cadd", 0.10, _SOURCE_WEIGHTS["cadd"], "Low CADD"),
        ]
        result = engine._aggregate(evidences)
        # Should NOT use override because cadd says benign
        assert result.composite_score != 0.95

    def test_clinvar_dedup_prefers_api(self, engine):
        evidences = [
            SourceEvidence("clinvar", 0.95, _SOURCE_WEIGHTS["clinvar"], "Pathogenic"),
            SourceEvidence("clinvar_local", 0.80, _SOURCE_WEIGHTS["clinvar_local"], "Likely path"),
        ]
        result = engine._aggregate(evidences)
        # clinvar_local should be dropped
        assert "clinvar_local" not in result.sources

    def test_weighted_average(self, engine):
        evidences = [
            SourceEvidence("cadd", 0.60, _SOURCE_WEIGHTS["cadd"], "Medium"),
            SourceEvidence("gnomad_af", 0.40, _SOURCE_WEIGHTS["gnomad_af"], "Moderate freq"),
        ]
        result = engine._aggregate(evidences)
        assert result.composite_score > 0.0
        assert result.evidence_count == 2

    def test_result_has_sources(self, engine):
        evidences = [
            SourceEvidence("cadd", 0.70, _SOURCE_WEIGHTS["cadd"], "High CADD"),
        ]
        result = engine._aggregate(evidences)
        assert "cadd" in result.sources

    def test_conflicts_detected_in_aggregate(self, engine):
        evidences = [
            SourceEvidence("clinvar", 0.10, _SOURCE_WEIGHTS["clinvar"], "Benign"),
            SourceEvidence("cadd", 0.90, _SOURCE_WEIGHTS["cadd"], "High CADD"),
        ]
        result = engine._aggregate(evidences)
        assert len(result.conflicts) > 0


class TestScoreVariant:
    def test_empty_annotations(self, engine):
        result = engine.score_variant({})
        assert "composite_score" in result
        assert "confidence" in result
        assert "classification" in result
        assert "evidence_count" in result

    def test_full_annotation(self, engine):
        annotations = {
            "clinvar": {"found": True, "clinical_significance": "Pathogenic"},
            "gnomad": {
                "found": True,
                "cadd": {"phred": 30},
                "af": 0.00005,
            },
            "alpha_missense": {"am_pathogenicity": 0.90},
            "ensembl": {
                "found": True,
                "data": [{"most_severe_consequence": "stop_gained"}]
            },
        }
        result = engine.score_variant(annotations)
        assert result["composite_score"] > 0.0
        assert result["evidence_count"] >= 3

    def test_only_benign_clinvar(self, engine):
        annotations = {
            "clinvar": {"found": True, "clinical_significance": "Benign"},
        }
        result = engine.score_variant(annotations)
        assert result["classification"] in ("benign", "likely_benign", "uncertain")

    def test_returns_dict(self, engine):
        result = engine.score_variant({"clinvar": {"found": False}})
        assert isinstance(result, dict)


class TestScoringResult:
    def test_to_dict_keys(self):
        result = ScoringResult(
            composite_score=0.75,
            confidence="high",
            evidence_count=3,
            classification="likely_pathogenic",
            sources={"clinvar": {"score": 0.95}},
            conflicts=[],
            total_weight=0.55,
        )
        d = result.to_dict()
        assert d["composite_score"] == 0.75
        assert d["confidence"] == "high"
        assert d["evidence_count"] == 3
        assert d["classification"] == "likely_pathogenic"
        assert "sources" in d
        assert "conflicts" in d
        assert "total_weight" in d

    def test_to_dict_rounds_values(self):
        result = ScoringResult(composite_score=0.123456789, total_weight=0.123456789)
        d = result.to_dict()
        assert d["composite_score"] == 0.1235
        assert d["total_weight"] == 0.123


class TestGetScoringEngine:
    def test_returns_instance(self):
        engine = get_scoring_engine()
        assert isinstance(engine, ScoringEngine)

    def test_singleton(self):
        e1 = get_scoring_engine()
        e2 = get_scoring_engine()
        assert e1 is e2


class TestScoreAlphaFold:
    def setup_method(self):
        self.engine = ScoringEngine()

    def test_none_data(self):
        assert self.engine._score_alphafold(None) is None

    def test_not_found(self):
        assert self.engine._score_alphafold({"found": False}) is None

    def test_high_confidence(self):
        ev = self.engine._score_alphafold({"found": True, "global_confidence": 92.5})
        assert ev is not None
        assert ev.score == 0.60

    def test_medium_confidence(self):
        ev = self.engine._score_alphafold({"found": True, "global_confidence": 75.0})
        assert ev is not None
        assert ev.score == 0.45

    def test_low_confidence(self):
        ev = self.engine._score_alphafold({"found": True, "global_confidence": 55.0})
        assert ev is not None
        assert ev.score == 0.30

    def test_very_low_confidence(self):
        ev = self.engine._score_alphafold({"found": True, "global_confidence": 30.0})
        assert ev is not None
        assert ev.score == 0.15


class TestScoreLitvar:
    def setup_method(self):
        self.engine = ScoringEngine()

    def test_none_data(self):
        assert self.engine._score_litvar(None) is None

    def test_not_found(self):
        assert self.engine._score_litvar({"found": False}) is None

    def test_many_publications(self):
        ev = self.engine._score_litvar({"found": True, "total_publications": 500})
        assert ev is not None
        assert ev.score == 0.55

    def test_moderate_publications(self):
        ev = self.engine._score_litvar({"found": True, "total_publications": 25})
        assert ev is not None
        assert ev.score == 0.50

    def test_few_publications(self):
        ev = self.engine._score_litvar({"found": True, "total_publications": 3})
        assert ev is not None
        assert ev.score == 0.40

    def test_zero_publications(self):
        assert self.engine._score_litvar({"found": True, "total_publications": 0}) is None


class TestScoreGeneConstraint:
    def setup_method(self):
        self.engine = ScoringEngine()

    def test_none_data(self):
        assert self.engine._score_gene_constraint(None) is None

    def test_no_pli_no_loeuf(self):
        assert self.engine._score_gene_constraint({"pli": None, "loeuf": None}) is None

    def test_low_loeuf_highly_constrained(self):
        ev = self.engine._score_gene_constraint({"pli": None, "loeuf": 0.2})
        assert ev is not None
        assert ev.score == 0.75

    def test_medium_loeuf(self):
        ev = self.engine._score_gene_constraint({"pli": None, "loeuf": 0.5})
        assert ev is not None
        assert ev.score == 0.55

    def test_high_loeuf_tolerant(self):
        ev = self.engine._score_gene_constraint({"pli": None, "loeuf": 1.2})
        assert ev is not None
        assert ev.score == 0.25

    def test_high_pli(self):
        ev = self.engine._score_gene_constraint({"pli": 0.95, "loeuf": None})
        assert ev is not None
        assert ev.score == 0.70

    def test_loeuf_preferred_over_pli(self):
        ev = self.engine._score_gene_constraint({"pli": 0.95, "loeuf": 0.2})
        assert ev is not None
        assert ev.score == 0.75  # LOEUF takes priority


class TestScoreClinvarGeneStats:
    def setup_method(self):
        self.engine = ScoringEngine()

    def test_none_data(self):
        assert self.engine._score_clinvar_gene_stats(None) is None

    def test_too_few_submissions(self):
        assert self.engine._score_clinvar_gene_stats({"total_submissions": 3, "pathogenic_count": 2}) is None

    def test_high_pathogenic_ratio(self):
        ev = self.engine._score_clinvar_gene_stats({"total_submissions": 100, "pathogenic_count": 40})
        assert ev is not None
        assert ev.score == 0.70

    def test_medium_pathogenic_ratio(self):
        ev = self.engine._score_clinvar_gene_stats({"total_submissions": 100, "pathogenic_count": 20})
        assert ev is not None
        assert ev.score == 0.55

    def test_low_pathogenic_ratio(self):
        ev = self.engine._score_clinvar_gene_stats({"total_submissions": 100, "pathogenic_count": 8})
        assert ev is not None
        assert ev.score == 0.40

    def test_very_low_pathogenic_ratio(self):
        ev = self.engine._score_clinvar_gene_stats({"total_submissions": 100, "pathogenic_count": 2})
        assert ev is not None
        assert ev.score == 0.20


class TestScoreChembl:
    def setup_method(self):
        self.engine = ScoringEngine()

    def test_none_data(self):
        assert self.engine._score_chembl(None) is None

    def test_not_found(self):
        assert self.engine._score_chembl({"found": False}) is None

    def test_no_drugs(self):
        assert self.engine._score_chembl({"found": True, "drugs": []}) is None

    def test_approved_with_warnings(self):
        data = {
            "found": True,
            "drugs": [{"max_phase": 4}],
            "warnings": [{"warning_type": "Black Box"}],
        }
        ev = self.engine._score_chembl(data)
        assert ev is not None
        assert ev.score == 0.65

    def test_approved_no_warnings(self):
        data = {"found": True, "drugs": [{"max_phase": 4}], "warnings": []}
        ev = self.engine._score_chembl(data)
        assert ev is not None
        assert ev.score == 0.55

    def test_many_drugs_no_approved(self):
        data = {"found": True, "drugs": [{"max_phase": 2}] * 6, "warnings": []}
        ev = self.engine._score_chembl(data)
        assert ev is not None
        assert ev.score == 0.45

    def test_few_drugs_no_approved(self):
        data = {"found": True, "drugs": [{"max_phase": 1}], "warnings": []}
        ev = self.engine._score_chembl(data)
        assert ev is not None
        assert ev.score == 0.35


class TestScoreFdaDrug:
    def setup_method(self):
        self.engine = ScoringEngine()

    def test_none_data(self):
        assert self.engine._score_fda_drug(None) is None

    def test_not_found(self):
        assert self.engine._score_fda_drug({"found": False}) is None

    def test_no_labels(self):
        assert self.engine._score_fda_drug({"found": True, "labels": []}) is None

    def test_cyp_with_interactions(self):
        data = {
            "found": True,
            "labels": [{"cyp_enzymes": ["CYP3A4"], "drug_interactions": "some text"}],
        }
        ev = self.engine._score_fda_drug(data)
        assert ev is not None
        assert ev.score == 0.60

    def test_cyp_no_interactions(self):
        data = {
            "found": True,
            "labels": [{"cyp_enzymes": ["CYP2D6"], "drug_interactions": ""}],
        }
        ev = self.engine._score_fda_drug(data)
        assert ev is not None
        assert ev.score == 0.50

    def test_interactions_no_cyp(self):
        data = {
            "found": True,
            "labels": [{"cyp_enzymes": [], "drug_interactions": "interacts with warfarin"}],
        }
        ev = self.engine._score_fda_drug(data)
        assert ev is not None
        assert ev.score == 0.45

    def test_labels_only(self):
        data = {
            "found": True,
            "labels": [{"cyp_enzymes": [], "drug_interactions": ""}],
        }
        ev = self.engine._score_fda_drug(data)
        assert ev is not None
        assert ev.score == 0.35


class TestScoreGnomadTx:
    def setup_method(self):
        self.engine = ScoringEngine()

    def test_none_data(self):
        assert self.engine._score_gnomad_tx(None) is None

    def test_not_found(self):
        assert self.engine._score_gnomad_tx({"found": False}) is None

    def test_hc_lof(self):
        ev = self.engine._score_gnomad_tx({"found": True, "lof": "HC", "mean_expression": 0.8})
        assert ev is not None
        assert ev.score == 0.80

    def test_lc_lof(self):
        ev = self.engine._score_gnomad_tx({"found": True, "lof": "LC", "mean_expression": 0.3})
        assert ev is not None
        assert ev.score == 0.55

    def test_high_expression_no_lof(self):
        ev = self.engine._score_gnomad_tx({"found": True, "lof": None, "mean_expression": 0.7})
        assert ev is not None
        assert ev.score == 0.45

    def test_moderate_expression_no_lof(self):
        ev = self.engine._score_gnomad_tx({"found": True, "lof": None, "mean_expression": 0.3})
        assert ev is not None
        assert ev.score == 0.35

    def test_low_expression_no_lof_returns_none(self):
        assert self.engine._score_gnomad_tx({"found": True, "lof": None, "mean_expression": 0.05}) is None
