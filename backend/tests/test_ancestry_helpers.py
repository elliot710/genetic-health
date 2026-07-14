"""Tests for pure helper functions in ancestry.py insight generator."""
import math
from unittest.mock import patch


class TestClassifyGenotype:
    """Tests for _classify_genotype."""

    def _fn(self):
        from backend.services.insight_generators.ancestry import _classify_genotype
        return _classify_genotype

    def test_hom_ref_slash_separated(self):
        assert self._fn()("A/A", "A", "T") == "hom_ref"

    def test_hom_alt_slash_separated(self):
        assert self._fn()("T/T", "A", "T") == "hom_alt"

    def test_het_slash_separated(self):
        assert self._fn()("A/T", "A", "T") == "het"

    def test_pipe_separated(self):
        assert self._fn()("A|T", "A", "T") == "het"

    def test_two_char_no_separator(self):
        assert self._fn()("AT", "A", "T") == "het"

    def test_two_same_char_no_separator(self):
        assert self._fn()("AA", "A", "T") == "hom_ref"

    def test_returns_none_for_empty(self):
        assert self._fn()(None, "A", "T") is None

    def test_returns_none_for_single_char(self):
        assert self._fn()("A", "A", "T") is None

    def test_no_ref_alt_heterozygous(self):
        assert self._fn()("A/T", None, None) == "het"

    def test_no_ref_alt_homozygous(self):
        assert self._fn()("A/A", None, None) == "hom_ref"

    def test_mismatched_alleles_treated_as_het(self):
        assert self._fn()("A/G", "A", "T") == "het"


class TestGenotypeLogLikelihood:
    """Tests for _genotype_log_likelihood."""

    def _fn(self):
        from backend.services.insight_generators.ancestry import _genotype_log_likelihood
        return _genotype_log_likelihood

    def test_returns_float(self):
        result = self._fn()(0.5, "het")
        assert isinstance(result, float)

    def test_hom_ref_at_low_af_has_high_ll(self):
        ll_ref = self._fn()(0.05, "hom_ref")
        ll_alt = self._fn()(0.05, "hom_alt")
        assert ll_ref > ll_alt

    def test_hom_alt_at_high_af_has_high_ll(self):
        ll_alt = self._fn()(0.95, "hom_alt")
        ll_ref = self._fn()(0.95, "hom_ref")
        assert ll_alt > ll_ref

    def test_het_maximized_near_0_5_af(self):
        ll_half = self._fn()(0.5, "het")
        ll_low = self._fn()(0.1, "het")
        assert ll_half > ll_low

    def test_result_is_log_probability_negative(self):
        result = self._fn()(0.3, "het")
        assert result < 0

    def test_extreme_af_clamped(self):
        ll_zero = self._fn()(0.0, "hom_alt")
        ll_small = self._fn()(0.001, "hom_alt")
        assert abs(ll_zero - ll_small) < 0.01


class TestComputeNeanderthal:
    """Tests for _compute_neanderthal."""

    def _fn(self):
        from backend.services.insight_generators.ancestry import _compute_neanderthal
        return _compute_neanderthal

    def test_returns_dict_with_expected_keys(self):
        result = self._fn()(set(), 100)
        assert all(k in result for k in ["percentage", "variants", "moreOrLess", "comparison"])

    def test_empty_set_zero_percent(self):
        result = self._fn()(set(), 100)
        assert result["percentage"] == 0.0
        assert result["variants"] == 0

    def test_overlapping_rsids_increases_percentage(self):
        from backend.services.insight_generators.ancestry import NEANDERTHAL_RSIDS
        user_rsids = set(list(NEANDERTHAL_RSIDS)[:5])
        result = self._fn()(user_rsids, 100)
        assert result["percentage"] > 0
        assert result["variants"] == 5

    def test_percentage_capped_at_4(self):
        from backend.services.insight_generators.ancestry import NEANDERTHAL_RSIDS
        result = self._fn()(NEANDERTHAL_RSIDS, 100)
        assert result["percentage"] <= 4.0

    def test_more_when_percentage_above_2(self):
        from backend.services.insight_generators.ancestry import NEANDERTHAL_RSIDS
        result = self._fn()(NEANDERTHAL_RSIDS, 100)
        assert result["moreOrLess"] in ("more", "about average")

    def test_less_when_no_variants(self):
        result = self._fn()(set(), 100)
        assert result["moreOrLess"] == "less"


class TestBuildSubpopComposition:
    """Tests for _build_subpop_composition."""

    def _fn(self):
        from backend.services.insight_generators.ancestry import _build_subpop_composition
        return _build_subpop_composition

    def _make_defs(self):
        return {
            "nfe_nwe": {"label": "Northwestern European", "origin": "NW Europe", "description": "Dutch, German"},
            "fin": {"label": "Finnish", "origin": "Northern Europe", "description": "Finnish"},
        }

    def test_empty_pcts_returns_empty(self):
        result = self._fn()({}, 50.0, {})
        assert result == []

    def test_filters_small_contributions(self):
        result = self._fn()({"nfe_nwe": 0.1}, 50.0, self._make_defs())
        assert result == []

    def test_includes_contributions_above_threshold(self):
        result = self._fn()({"nfe_nwe": 60.0, "fin": 40.0}, 50.0, self._make_defs())
        assert len(result) == 2

    def test_sorted_descending_by_percentage(self):
        result = self._fn()({"nfe_nwe": 40.0, "fin": 60.0}, 50.0, self._make_defs())
        assert result[0]["percentage"] >= result[1]["percentage"]

    def test_scales_relative_to_eur_total(self):
        result = self._fn()({"nfe_nwe": 100.0}, 30.0, self._make_defs())
        assert len(result) == 1
        assert result[0]["percentage"] == 30.0

    def test_preserves_dropped_european_mass_as_remainder(self):
        # bgr survives; the small sub-pops are dropped — their European mass
        # must not vanish. It is preserved as an "Other European" remainder so
        # the composition still sums to (roughly) the European total.
        result = self._fn()(
            {"nfe_bgr": 40.0, "nfe_est": 0.2, "nfe_nwe": 0.2, "fin": 0.2},
            79.0, self._make_defs(),
        )
        assert abs(sum(e["percentage"] for e in result) - 79.0) < 1.0
        assert any(e["region"] == "Other European" for e in result)

    def test_no_remainder_when_entries_fully_allocate(self):
        result = self._fn()({"nfe_nwe": 100.0}, 30.0, self._make_defs())
        assert all(e["region"] != "Other European" for e in result)

    def test_no_remainder_when_all_dropped(self):
        # Nothing survives -> return empty; the super-pop fallback in
        # _build_full_composition preserves the European fraction instead.
        result = self._fn()({"nfe_nwe": 0.1}, 50.0, self._make_defs())
        assert result == []


class TestConfidenceBand:
    def _fn(self):
        from backend.services.insight_generators.ancestry import _confidence_band
        return _confidence_band

    def test_high_above_60(self):
        assert self._fn()(65.0) == "high"

    def test_moderate_between_35_and_60(self):
        assert self._fn()(40.0) == "moderate"

    def test_low_at_or_below_35(self):
        assert self._fn()(30.0) == "low"


class TestBuildFullComposition:
    """Tests for _build_full_composition."""

    def _fn(self):
        from backend.services.insight_generators.ancestry import _build_full_composition
        return _build_full_composition

    def _make_super_pcts(self):
        return {"afr": 10.0, "amr": 5.0, "eas": 5.0, "eur": 75.0, "sas": 5.0}

    def test_without_subpop_uses_superpop(self):
        result = self._fn()(self._make_super_pcts(), None)
        labels = [e["region"] for e in result]
        assert "European" in labels

    def test_with_subpop_replaces_eur(self):
        subpop = [{"region": "Northwestern European", "percentage": 75.0}]
        result = self._fn()(self._make_super_pcts(), subpop)
        labels = [e["region"] for e in result]
        assert "Northwestern European" in labels

    def test_filters_small_pops_without_subpop(self):
        pcts = {"afr": 0.1, "amr": 0.3, "eas": 0.2, "eur": 99.0, "sas": 0.4}
        result = self._fn()(pcts, None)
        assert len(result) == 1
        assert result[0]["region"] == "European"

    def test_returns_sorted_descending(self):
        result = self._fn()(self._make_super_pcts(), None)
        pcts = [e["percentage"] for e in result]
        assert pcts == sorted(pcts, reverse=True)
