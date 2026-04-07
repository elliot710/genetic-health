"""Additional tests for insight_generators/base.py uncovered sections."""
import pytest
from unittest.mock import MagicMock
from backend.services.insight_generators.base import (
    extract_gene_and_consequence,
    extract_frequency,
    get_ref_allele,
    get_annotation_ref_allele,
    get_annotation_allele_parts,
    risk_level_to_score,
    get_user_genotype,
    is_indel_genotype,
    is_no_call_genotype,
    _parse_alleles,
    is_heterozygous,
    zygosity_adjust,
    boost_if_pathogenic,
    assess_risk_level,
    assess_drug_response,
    get_health_recommendations,
    get_drug_recommendations,
    get_trait_description,
)


def _make_annotation(data=None):
    ar = MagicMock()
    ar.annotation_data = data or {}
    ar.rsid = "rs12345"
    return ar


class TestExtractGeneAndConsequence:
    def test_no_annotation_result(self):
        gene, cons, impact = extract_gene_and_consequence(None, {})
        assert gene is None
        assert cons is None

    def test_no_annotation_data(self):
        ar = MagicMock()
        ar.annotation_data = None
        ar.rsid = "rs12345"
        gene, cons, impact = extract_gene_and_consequence(ar, {"rs12345": "BRCA1"})
        assert gene == "BRCA1"

    def test_ensembl_data(self):
        ar = _make_annotation({
            "annotations": {
                "ensembl": {
                    "data": [{
                        "transcript_consequences": [{
                            "gene_symbol": "TP53",
                            "consequence_terms": ["stop_gained"],
                            "impact": "HIGH"
                        }]
                    }]
                }
            }
        })
        gene, cons, impact = extract_gene_and_consequence(ar, {})
        assert gene == "TP53"
        assert cons == "stop_gained"
        assert impact == "HIGH"

    def test_clinvar_local_fallback(self):
        ar = _make_annotation({
            "annotations": {
                "clinvar_local": {
                    "found": True,
                    "genes": ["BRCA2"],
                    "molecular_consequence": "missense"
                }
            }
        })
        gene, cons, impact = extract_gene_and_consequence(ar, {})
        assert gene == "BRCA2"
        assert cons == "missense"

    def test_gnomad_fallback(self):
        ar = _make_annotation({
            "annotations": {
                "gnomad": {
                    "found": True,
                    "gene": "CFTR",
                    "consequence": "frameshift",
                    "impact": "HIGH"
                }
            }
        })
        gene, cons, impact = extract_gene_and_consequence(ar, {})
        assert gene == "CFTR"

    def test_rsid_gene_map_fallback(self):
        ar = _make_annotation({"annotations": {}})
        ar.rsid = "rs999"
        gene, cons, impact = extract_gene_and_consequence(ar, {"rs999": "MTHFR"})
        assert gene == "MTHFR"

    def test_ensembl_no_gene_symbol_uses_rsid_map(self):
        ar = _make_annotation({
            "annotations": {
                "ensembl": {
                    "data": [{
                        "transcript_consequences": [{
                            "consequence_terms": ["missense_variant"],
                            "impact": "MODERATE"
                        }]
                    }]
                }
            }
        })
        ar.rsid = "rs123"
        gene, cons, impact = extract_gene_and_consequence(ar, {"rs123": "GENE_X"})
        assert gene == "GENE_X"
        assert cons == "missense_variant"


class TestExtractFrequency:
    def test_none_annotation(self):
        assert extract_frequency(None) == 0.0

    def test_no_annotation_data(self):
        ar = MagicMock()
        ar.annotation_data = None
        assert extract_frequency(ar) == 0.0

    def test_gnomad_af(self):
        ar = _make_annotation({
            "annotations": {
                "gnomad": {"found": True, "af": 0.001}
            }
        })
        assert extract_frequency(ar) == pytest.approx(0.001)

    def test_thousand_genomes(self):
        ar = _make_annotation({
            "annotations": {
                "thousand_genomes": {"found": True, "global_af": 0.05}
            }
        })
        assert extract_frequency(ar) == pytest.approx(0.05)

    def test_ensembl_colocated(self):
        ar = _make_annotation({
            "annotations": {
                "ensembl": {
                    "data": [{
                        "colocated_variants": [{
                            "frequencies": {
                                "A": {"gnomade": 0.002}
                            }
                        }]
                    }]
                }
            }
        })
        assert extract_frequency(ar) == pytest.approx(0.002)

    def test_returns_zero_when_no_frequency(self):
        ar = _make_annotation({"annotations": {}})
        assert extract_frequency(ar) == 0.0


class TestGetRefAllele:
    def test_no_marker(self):
        v = MagicMock()
        v.marker = None
        assert get_ref_allele(v) is None

    def test_valid_ref_allele(self):
        v = MagicMock()
        v.marker.ref_allele = "A"
        assert get_ref_allele(v) == "A"

    def test_n_ref_allele_excluded(self):
        v = MagicMock()
        v.marker.ref_allele = "N"
        assert get_ref_allele(v) is None

    def test_dash_ref_allele_excluded(self):
        v = MagicMock()
        v.marker.ref_allele = "-"
        assert get_ref_allele(v) is None


class TestGetAnnotationRefAllele:
    def test_none_annotation(self):
        assert get_annotation_ref_allele(None) is None

    def test_clinvar_local_ref(self):
        ar = _make_annotation({
            "annotations": {
                "clinvar_local": {"found": True, "ref_allele": "G"}
            }
        })
        assert get_annotation_ref_allele(ar) == "G"

    def test_ensembl_allele_string(self):
        ar = _make_annotation({
            "annotations": {
                "ensembl": {
                    "data": [{"allele_string": "A/T"}]
                }
            }
        })
        assert get_annotation_ref_allele(ar) == "A"

    def test_gnomad_ref(self):
        ar = _make_annotation({
            "annotations": {
                "gnomad": {"found": True, "ref": "C"}
            }
        })
        assert get_annotation_ref_allele(ar) == "C"

    def test_n_allele_excluded(self):
        ar = _make_annotation({
            "annotations": {
                "clinvar_local": {"found": True, "ref_allele": "N"}
            }
        })
        assert get_annotation_ref_allele(ar) is None


class TestGetAnnotationAlleleParts:
    def test_none_annotation(self):
        assert get_annotation_allele_parts(None) == (None, None)

    def test_ensembl_allele_string(self):
        ar = _make_annotation({
            "annotations": {
                "ensembl": {
                    "data": [{"allele_string": "A/T"}]
                }
            }
        })
        ref, alt = get_annotation_allele_parts(ar)
        assert ref == "A"
        assert alt == "T"

    def test_gnomad_parts(self):
        ar = _make_annotation({
            "annotations": {
                "gnomad": {"found": True, "ref": "C", "alt": "G"}
            }
        })
        ref, alt = get_annotation_allele_parts(ar)
        assert ref == "C"
        assert alt == "G"

    def test_clinvar_local_parts(self):
        ar = _make_annotation({
            "annotations": {
                "clinvar_local": {
                    "found": True,
                    "ref_allele": "A",
                    "alt_allele": "T"
                }
            }
        })
        ref, alt = get_annotation_allele_parts(ar)
        assert ref == "A"
        assert alt == "T"

    def test_multiallelic_alt(self):
        ar = _make_annotation({
            "annotations": {
                "ensembl": {
                    "data": [{"allele_string": "C/A,G"}]
                }
            }
        })
        ref, alt = get_annotation_allele_parts(ar)
        assert ref == "C"
        assert alt == "A,G"


class TestRiskLevelToScore:
    def test_all_levels(self):
        assert risk_level_to_score("low") == pytest.approx(0.2)
        assert risk_level_to_score("average") == pytest.approx(0.4)
        assert risk_level_to_score("moderate") == pytest.approx(0.6)
        assert risk_level_to_score("high") == pytest.approx(0.8)
        assert risk_level_to_score("very_high") == pytest.approx(0.95)
        assert risk_level_to_score("unknown") == pytest.approx(0.0)

    def test_unknown_level_default(self):
        assert risk_level_to_score("something_else") == pytest.approx(0.5)

    def test_case_insensitive(self):
        assert risk_level_to_score("HIGH") == pytest.approx(0.8)

    def test_strip_spaces(self):
        assert risk_level_to_score("  low  ") == pytest.approx(0.2)

    def test_space_variant(self):
        assert risk_level_to_score("very high") == pytest.approx(0.95)


class TestGetUserGenotype:
    def test_genotype_attribute(self):
        v = MagicMock()
        v.genotype = "AG"
        assert get_user_genotype(v) == "AG"

    def test_falls_back_to_info(self):
        v = MagicMock()
        v.genotype = None
        v.info = {"original_genotype": "ct"}
        assert get_user_genotype(v) == "CT"

    def test_returns_none_when_empty(self):
        v = MagicMock()
        v.genotype = None
        v.info = {}
        assert get_user_genotype(v) is None

    def test_strips_whitespace(self):
        v = MagicMock()
        v.genotype = "  AG  "
        assert get_user_genotype(v) == "AG"


class TestIsIndelGenotype:
    def test_ii_is_indel(self):
        assert is_indel_genotype("II") is True

    def test_dd_is_indel(self):
        assert is_indel_genotype("DD") is True

    def test_di_is_indel(self):
        assert is_indel_genotype("DI") is True

    def test_id_is_indel(self):
        assert is_indel_genotype("ID") is True

    def test_ag_not_indel(self):
        assert is_indel_genotype("AG") is False

    def test_none_not_indel(self):
        assert is_indel_genotype(None) is False


class TestIsNoCallGenotype:
    def test_double_dash_no_call(self):
        assert is_no_call_genotype("--") is True

    def test_zero_zero_no_call(self):
        assert is_no_call_genotype("00") is True

    def test_nc_no_call(self):
        assert is_no_call_genotype("NC") is True

    def test_none_no_call(self):
        assert is_no_call_genotype(None) is True

    def test_empty_string_no_call(self):
        assert is_no_call_genotype("") is True

    def test_valid_genotype_not_no_call(self):
        assert is_no_call_genotype("AG") is False

    def test_vcf_dot_slash_dot_no_call(self):
        assert is_no_call_genotype("./.") is True

    def test_vcf_dot_pipe_dot_no_call(self):
        assert is_no_call_genotype(".|.") is True


class TestParseAlleles:
    def test_slash_separated(self):
        alleles = _parse_alleles("A/G")
        assert alleles == ["A", "G"]

    def test_pipe_separated(self):
        alleles = _parse_alleles("A|G")
        assert alleles == ["A", "G"]

    def test_two_char_diploid(self):
        alleles = _parse_alleles("AG")
        assert alleles == ["A", "G"]

    def test_hemizygous_x(self):
        alleles = _parse_alleles("A")
        assert alleles == ["A"]

    def test_none_returns_none(self):
        assert _parse_alleles(None) is None

    def test_no_call_returns_none(self):
        assert _parse_alleles("--") is None

    def test_indel_code_split(self):
        alleles = _parse_alleles("DI")
        assert alleles == ["D", "I"]

    def test_dd_indel(self):
        alleles = _parse_alleles("DD")
        assert alleles == ["D", "D"]


class TestIsHeterozygous:
    def test_heterozygous_ag(self):
        assert is_heterozygous("AG") is True

    def test_homozygous_aa(self):
        assert is_heterozygous("AA") is False

    def test_slash_format(self):
        assert is_heterozygous("A/G") is True

    def test_hom_slash(self):
        assert is_heterozygous("A/A") is False

    def test_no_call(self):
        assert is_heterozygous("--") is False

    def test_none(self):
        assert is_heterozygous(None) is False


class TestZygosityAdjust:
    def test_homozygous_ref_deescalates(self):
        result = zygosity_adjust("moderate", "AA", ref_allele="A")
        assert result in ("low", "average")

    def test_heterozygous_unchanged(self):
        result = zygosity_adjust("moderate", "AG", ref_allele="A")
        assert result == "moderate"

    def test_hom_alt_escalates(self):
        result = zygosity_adjust("moderate", "GG", ref_allele="A")
        assert result in ("high", "very_high")

    def test_no_call_preserves_baseline(self):
        result = zygosity_adjust("moderate", "--")
        assert result == "moderate"

    def test_unknown_level_unchanged(self):
        result = zygosity_adjust("completely_unknown", "AG")
        assert result == "completely_unknown"

    def test_alias_variable_resolved(self):
        result = zygosity_adjust("variable", "AG")
        assert result == "average"

    def test_title_case_preserved(self):
        result = zygosity_adjust("Moderate", "AA", ref_allele="A")
        assert result[0].isupper()


class TestBoostIfPathogenic:
    def test_no_score_unchanged(self):
        assert boost_if_pathogenic("moderate", None) == "moderate"

    def test_non_dict_score_unchanged(self):
        assert boost_if_pathogenic("moderate", 0.9) == "moderate"

    def test_high_score_escalates(self):
        result = boost_if_pathogenic("moderate", {"composite_score": 0.85})
        assert result in ("high", "very_high")

    def test_low_score_unchanged(self):
        result = boost_if_pathogenic("moderate", {"composite_score": 0.5})
        assert result == "moderate"

    def test_boundary_exactly_080(self):
        result = boost_if_pathogenic("moderate", {"composite_score": 0.80})
        assert result in ("high", "very_high")

    def test_already_at_max_stays(self):
        result = boost_if_pathogenic("very_high", {"composite_score": 0.95})
        assert result == "very_high"

    def test_unknown_level_unchanged(self):
        result = boost_if_pathogenic("custom_level", {"composite_score": 0.95})
        assert result == "custom_level"


class TestAssessRiskLevel:
    def test_no_genotype_unknown(self):
        assert assess_risk_level("", 1.5) == "unknown"

    def test_no_call_unknown(self):
        assert assess_risk_level("--", 1.5) == "unknown"

    def test_high_composite_gives_high(self):
        result = assess_risk_level("AG", 2.0, pathogenicity_score={"composite_score": 0.85})
        assert result in ("high", "very_high")

    def test_moderate_composite_moderate_multiplier(self):
        result = assess_risk_level("AG", 2.0, pathogenicity_score={"composite_score": 0.65})
        assert result in ("moderate", "high")

    def test_low_composite_with_high_multiplier(self):
        result = assess_risk_level("AG", 2.5, pathogenicity_score={"composite_score": 0.10})
        assert result in ("low", "moderate")

    def test_no_score_multiplier_based(self):
        result = assess_risk_level("AG", 1.5)
        assert result == "moderate"

    def test_low_multiplier_no_score(self):
        result = assess_risk_level("AG", 0.7)
        assert result == "low"

    def test_zygosity_applied_hom_ref(self):
        result = assess_risk_level("GG", 1.5, ref_allele="G", pathogenicity_score={"composite_score": 0.85})
        # hom-ref should deescalate from high
        assert result in ("low", "average", "moderate")


class TestAssessDrugResponse:
    def test_no_genotype_normal(self):
        assert assess_drug_response("", "CYP2D6") == "normal"

    def test_hom_ref_normal(self):
        assert assess_drug_response("AA", "CYP2D6", ref_allele="A") == "normal"

    def test_cyp2c9_star2_poor(self):
        assert assess_drug_response("*2/*1", "CYP2C9") == "poor"

    def test_cyp2c9_star3_poor(self):
        assert assess_drug_response("*3/*1", "CYP2C9") == "poor"

    def test_cyp2c19_star2_poor(self):
        assert assess_drug_response("*2/*1", "CYP2C19") == "poor"

    def test_pharmacogene_hetero_intermediate(self):
        result = assess_drug_response("AG", "CYP2D6")
        assert result == "intermediate"

    def test_pharmacogene_hom_alt_poor(self):
        result = assess_drug_response("GG", "CYP2D6")
        assert result == "poor"

    def test_non_pharmacogene_normal(self):
        result = assess_drug_response("AG", "UNKNOWN_GENE")
        assert result == "normal"


class TestGetHealthRecommendations:
    def test_known_condition(self):
        result = get_health_recommendations("Type 2 Diabetes", "high")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_cardiovascular(self):
        result = get_health_recommendations("Cardiovascular Disease", "moderate")
        assert isinstance(result, list)

    def test_unknown_condition_default(self):
        result = get_health_recommendations("Rare Disease XYZ", "high")
        assert result == ["Consult with healthcare provider"]


class TestGetDrugRecommendations:
    def test_poor_metabolizer(self):
        result = get_drug_recommendations("Warfarin", "poor")
        assert "alternative" in result.lower() or "dosing" in result.lower()

    def test_intermediate(self):
        result = get_drug_recommendations("Clopidogrel", "intermediate")
        assert "monitor" in result.lower()

    def test_normal(self):
        result = get_drug_recommendations("Aspirin", "normal")
        assert "standard" in result.lower()


class TestGetTraitDescription:
    def test_returns_string(self):
        result = get_trait_description("Hair color", "Brown")
        assert isinstance(result, str)
        assert "Brown" in result
        assert "Hair color" in result
