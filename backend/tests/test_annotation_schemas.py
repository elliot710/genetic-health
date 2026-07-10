import pytest

from backend.db.annotation_schemas import validate_associated_variants


class TestValidateAssociatedVariants:
    def test_none_is_allowed(self):
        validate_associated_variants("HealthRisk", None)

    def test_list_of_strings_is_allowed(self):
        validate_associated_variants("HealthRisk", ["rs1001"])

    def test_empty_list_is_allowed(self):
        validate_associated_variants("HealthRisk", [])

    def test_bare_string_is_rejected(self):
        with pytest.raises(ValueError, match="associated_variants"):
            validate_associated_variants("HealthRisk", "rs1001")

    def test_list_with_non_string_item_is_rejected(self):
        with pytest.raises(ValueError, match="associated_variants"):
            validate_associated_variants("HealthRisk", [123])

    def test_dict_is_rejected(self):
        with pytest.raises(ValueError, match="associated_variants"):
            validate_associated_variants("HealthRisk", {"rsid": "rs1001"})

    def test_error_message_includes_model_name(self):
        with pytest.raises(ValueError, match="HealthRisk"):
            validate_associated_variants("HealthRisk", "rs1001")
