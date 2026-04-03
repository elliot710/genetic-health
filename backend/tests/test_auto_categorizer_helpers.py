"""Tests for pure static methods in AutoCategorizer."""
from unittest.mock import patch


class TestCleanCondition:
    """Tests for AutoCategorizer._clean_condition."""

    def _fn(self):
        from backend.services.auto_categorizer import AutoCategorizer
        return AutoCategorizer._clean_condition

    def test_returns_empty_for_empty_string(self):
        assert self._fn()("") == ""

    def test_returns_empty_for_none(self):
        assert self._fn()(None) == ""

    def test_returns_empty_for_not_provided(self):
        assert self._fn()("not provided") == ""

    def test_returns_empty_for_not_specified(self):
        assert self._fn()("not specified") == ""

    def test_returns_empty_for_dash(self):
        assert self._fn()("-") == ""

    def test_returns_plain_condition(self):
        assert self._fn()("Breast cancer") == "Breast cancer"

    def test_strips_whitespace(self):
        assert self._fn()("  BRCA1 variant  ") == "BRCA1 variant"

    def test_pipe_delimited_picks_first_valid(self):
        result = self._fn()("not provided|Hereditary breast carcinoma")
        assert result == "Hereditary breast carcinoma"

    def test_semicolon_delimited_picks_first_valid(self):
        result = self._fn()("not specified;Familial hypercholesterolemia")
        assert result == "Familial hypercholesterolemia"

    def test_all_parts_garbage_returns_empty(self):
        result = self._fn()("not provided|not specified")
        assert result == ""

    def test_uppercased_part_gets_titlecased(self):
        result = self._fn()("BRCA1 MUTATION|BRCA1 Mutation")
        assert result == "Brca1 Mutation"

    def test_single_valid_pipe_entry(self):
        result = self._fn()("Lynch syndrome|not provided")
        assert result == "Lynch syndrome"


class TestIsSelivereForCategory:
    """Tests for AutoCategorizer._is_severe_for_category."""

    def _fn(self):
        from backend.services.auto_categorizer import AutoCategorizer
        return AutoCategorizer._is_severe_for_category

    def test_returns_false_for_non_lifestyle_category(self):
        assert self._fn()("cancer", "health") is False

    def test_returns_false_for_non_severe_condition_in_lifestyle(self):
        from backend.services import multi_source_categorizer as msc
        msc._SEVERE_EXCLUSION_KW.clear()
        assert self._fn()("endurance capacity", "sports") is False

    def test_returns_true_for_severe_keyword_in_lifestyle(self):
        from backend.services import multi_source_categorizer as msc
        msc._SEVERE_EXCLUSION_KW.clear()
        msc._SEVERE_EXCLUSION_KW.add("cancer")
        result = self._fn()("breast cancer", "sports")
        msc._SEVERE_EXCLUSION_KW.clear()
        assert result is True

    def test_returns_false_severe_keyword_not_in_non_lifestyle(self):
        from backend.services import multi_source_categorizer as msc
        msc._SEVERE_EXCLUSION_KW.clear()
        msc._SEVERE_EXCLUSION_KW.add("tumor")
        result = self._fn()("tumor", "health")
        msc._SEVERE_EXCLUSION_KW.clear()
        assert result is False

    def test_case_insensitive_keyword_match(self):
        from backend.services import multi_source_categorizer as msc
        msc._SEVERE_EXCLUSION_KW.clear()
        msc._SEVERE_EXCLUSION_KW.add("cancer")
        result = self._fn()("BREAST CANCER", "wellness")
        msc._SEVERE_EXCLUSION_KW.clear()
        assert result is True


class TestRiskMultiplierFromReviewStatus:
    """Tests for AutoCategorizer._risk_multiplier_from_review_status."""

    def _fn(self):
        from backend.services.auto_categorizer import AutoCategorizer
        return AutoCategorizer._risk_multiplier_from_review_status

    def test_practice_guideline_pathogenic_returns_3(self):
        assert self._fn()("practice guideline", "Pathogenic") == 3.0

    def test_expert_panel_pathogenic_returns_2(self):
        assert self._fn()("reviewed by expert panel", "Pathogenic") == 2.0

    def test_multiple_submitters_pathogenic_returns_1_5(self):
        assert self._fn()("criteria provided, multiple submitters", "Pathogenic") == 1.5

    def test_single_submitter_pathogenic_returns_1_2(self):
        assert self._fn()("criteria provided, single submitter", "Pathogenic") == 1.2

    def test_likely_pathogenic_gets_80_percent_of_pathogenic(self):
        result = self._fn()("practice guideline", "Likely pathogenic")
        assert result == round(3.0 * 0.8, 2)

    def test_likely_detected_in_sig_string(self):
        result = self._fn()("expert panel", "Likely_pathogenic")
        assert result < 2.0

    def test_empty_review_status_falls_back_to_1_2(self):
        assert self._fn()("", "Pathogenic") == 1.2

    def test_none_review_status_falls_back_to_1_2(self):
        assert self._fn()(None, "Pathogenic") == 1.2

    def test_no_conflicts_maps_to_1_5(self):
        result = self._fn()("criteria provided, no conflicts", "Pathogenic")
        assert result == 1.5


class TestPopulateCategoryFields:
    """Tests for AutoCategorizer._populate_category_fields."""

    def _fn(self):
        from backend.services.auto_categorizer import AutoCategorizer
        return AutoCategorizer._populate_category_fields

    def test_health_sets_condition_as_primary(self):
        data = {}
        with patch('backend.services.multi_source_categorizer._category_aware_label',
                   return_value='label'):
            from backend.services.auto_categorizer import AutoCategorizer
            AutoCategorizer._populate_category_fields(data, 'health', 'BRCA1 variant', 'BRCA1')
        assert data.get('condition') == 'BRCA1 variant'

    def test_nutrition_sets_nutrient_as_primary(self):
        data = {}
        with patch('backend.services.multi_source_categorizer._category_aware_label',
                   return_value='label'):
            from backend.services.auto_categorizer import AutoCategorizer
            AutoCategorizer._populate_category_fields(data, 'nutrition', 'Folate metabolism', 'MTHFR')
        assert data.get('nutrient') == 'Folate metabolism'

    def test_drug_response_sets_drug_as_primary(self):
        data = {}
        with patch('backend.services.multi_source_categorizer._category_aware_label',
                   return_value='label'):
            from backend.services.auto_categorizer import AutoCategorizer
            AutoCategorizer._populate_category_fields(data, 'drug_response', 'Warfarin sensitivity', 'VKORC1')
        assert data.get('drug') == 'Warfarin sensitivity'

    def test_does_not_overwrite_existing_fields(self):
        data = {'condition': 'existing_value'}
        with patch('backend.services.multi_source_categorizer._category_aware_label',
                   return_value='label'):
            from backend.services.auto_categorizer import AutoCategorizer
            AutoCategorizer._populate_category_fields(data, 'health', 'new_condition', 'GENE1')
        assert data['condition'] == 'existing_value'
