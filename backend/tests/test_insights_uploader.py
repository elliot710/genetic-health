"""Tests for insights_service.py and variant_uploader.py."""
import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
import importlib.util as _ilu
import os


def _load_insights_service():
    spec = _ilu.spec_from_file_location(
        "_insights_svc",
        os.path.join(os.path.dirname(__file__), '..', 'services', 'insights_service.py'),
    )
    mod = _ilu.module_from_spec(spec)
    with patch.dict('sys.modules', {
        'aiohttp': MagicMock(),
        'backend.db.models': MagicMock(),
        'backend.db.database': MagicMock(),
    }):
        spec.loader.exec_module(mod)
    return mod


_is = _load_insights_service()


# ──────────────────────────────────────────────
# insights_service pure functions
# ──────────────────────────────────────────────

class TestLoadEnabledState:
    def test_env_var_true(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        with patch.dict(os.environ, {'AI_INSIGHTS_ENABLED': 'true'}), \
             patch.object(_is, '_STATE_FILE', mock_path):
            assert _is._load_enabled_state() is True

    def test_env_var_1(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        with patch.dict(os.environ, {'AI_INSIGHTS_ENABLED': '1'}), \
             patch.object(_is, '_STATE_FILE', mock_path):
            assert _is._load_enabled_state() is True

    def test_env_var_false(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        with patch.dict(os.environ, {'AI_INSIGHTS_ENABLED': 'false'}), \
             patch.object(_is, '_STATE_FILE', mock_path):
            assert _is._load_enabled_state() is False

    def test_state_file_1(self, tmp_path):
        f = tmp_path / ".insights_state"
        f.write_text("1")
        with patch.object(_is, '_STATE_FILE', f):
            assert _is._load_enabled_state() is True

    def test_state_file_0(self, tmp_path):
        f = tmp_path / ".insights_state"
        f.write_text("0")
        with patch.object(_is, '_STATE_FILE', f):
            assert _is._load_enabled_state() is False

    def test_state_file_read_error(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.side_effect = OSError("no perm")
        with patch.dict(os.environ, {'AI_INSIGHTS_ENABLED': 'false'}), \
             patch.object(_is, '_STATE_FILE', mock_path):
            result = _is._load_enabled_state()
            assert result is False


class TestLoadSystemPrompt:
    def test_loads_from_file(self, tmp_path):
        f = tmp_path / "system.md"
        f.write_text("You are a helpful assistant.")
        with patch.object(_is, '_PROMPT_FILE', f):
            prompt = _is._load_system_prompt()
            assert "helpful assistant" in prompt

    def test_fallback_when_missing(self):
        missing = _is._PROMPT_FILE.parent / "nonexistent_prompt_file.md"
        with patch.object(_is, '_PROMPT_FILE', missing):
            prompt = _is._load_system_prompt()
            assert "genomics" in prompt.lower() or "genetic" in prompt.lower()


class TestIsExpressMode:
    def test_express_key_starts_with_AQ(self):
        assert _is._is_express_mode_key("AQ.somekey") is True

    def test_ai_studio_key(self):
        assert _is._is_express_mode_key("AIzaSyXXXXX") is False

    def test_empty_key(self):
        assert _is._is_express_mode_key("") is False

    def test_none_like_empty(self):
        assert _is._is_express_mode_key("") is False


class TestIsStandardVertexKey:
    def test_standard_vertex_key(self):
        assert _is._is_standard_vertex_key("some-project-key") is True

    def test_ai_studio_key_not_standard(self):
        assert _is._is_standard_vertex_key("AIzaSyXXXXX") is False

    def test_aq_key_not_standard(self):
        assert _is._is_standard_vertex_key("AQ.somekey") is False

    def test_empty_key_not_standard(self):
        assert _is._is_standard_vertex_key("") is False


class TestBuildUserPrompt:
    def test_overview_section(self):
        data = {"summary": {"total_variants": 100}, "health_risks": [], "drug_responses": [], "carrier_status": [], "rare_mutations": [], "uncommon_mutations": []}
        prompt = _is._build_user_prompt("overview", data)
        assert "overview" in prompt.lower() or "profile" in prompt.lower()

    def test_health_section(self):
        data = {"health_risks": [{"condition": "Diabetes", "risk_level": "high"}]}
        prompt = _is._build_user_prompt("health", data)
        assert "health" in prompt.lower() or "risk" in prompt.lower()

    def test_drug_responses_section(self):
        data = {"drug_responses": [{"drug": "Warfarin", "gene": "CYP2C9"}]}
        prompt = _is._build_user_prompt("drug_responses", data)
        assert "drug" in prompt.lower() or "pharmaco" in prompt.lower()

    def test_carrier_status_section(self):
        data = {"carrier_status": [{"condition": "CF"}]}
        prompt = _is._build_user_prompt("carrier_status", data)
        assert "carrier" in prompt.lower()

    def test_ancestry_section(self):
        data = {"ancestry_results": [{"population": "European"}]}
        prompt = _is._build_user_prompt("ancestry", data)
        assert "ancestry" in prompt.lower() or "population" in prompt.lower()

    def test_personality_section(self):
        data = {"personality_traits": [{"trait": "openness"}]}
        prompt = _is._build_user_prompt("personality", data)
        assert "personality" in prompt.lower()

    def test_intelligence_section(self):
        data = {"intelligence": [{"ability": "processing_speed"}]}
        prompt = _is._build_user_prompt("intelligence", data)
        assert "cognitive" in prompt.lower() or "intelligence" in prompt.lower()

    def test_wellness_section(self):
        data = {"wellness_traits": [{"trait": "sleep"}]}
        prompt = _is._build_user_prompt("wellness", data)
        assert "wellness" in prompt.lower()

    def test_methylation_section(self):
        data = {"methylation_profiles": [{"gene": "MTHFR"}]}
        prompt = _is._build_user_prompt("methylation", data)
        assert "methylation" in prompt.lower()

    def test_detox_section(self):
        data = {"detoxification_profiles": [{"phase": "1"}]}
        prompt = _is._build_user_prompt("detox", data)
        assert "detox" in prompt.lower()

    def test_nutrition_section(self):
        data = {"nutrition_traits": [{"nutrient": "folate"}]}
        prompt = _is._build_user_prompt("nutrition", data)
        assert "nutrition" in prompt.lower()

    def test_sports_section(self):
        data = {"sports_performance": [{"category": "endurance"}]}
        prompt = _is._build_user_prompt("sports", data)
        assert "sport" in prompt.lower()

    def test_physical_traits_section(self):
        data = {"physical_traits": [{"trait": "height"}]}
        prompt = _is._build_user_prompt("physical_traits", data)
        assert "physical" in prompt.lower()

    def test_rare_mutations_section(self):
        data = {"rare_mutations": [{"gene": "BRCA1"}]}
        prompt = _is._build_user_prompt("rare_mutations", data)
        assert "rare" in prompt.lower() or "mutation" in prompt.lower()

    def test_uncommon_mutations_section(self):
        data = {"uncommon_mutations": [{"gene": "TP53"}]}
        prompt = _is._build_user_prompt("uncommon_mutations", data)
        assert "uncommon" in prompt.lower() or "mutation" in prompt.lower()

    def test_unknown_section_fallback(self):
        data = {"mydata": [{"item": "value"}]}
        prompt = _is._build_user_prompt("mydata", data)
        assert "mydata" in prompt

    def test_empty_data(self):
        prompt = _is._build_user_prompt("health", {})
        assert "health" in prompt.lower() or "risk" in prompt.lower()


class TestBuildVariantPrompt:
    def test_basic_variant(self):
        data = {"rsid": "rs123", "gene": "BRCA1", "clinical_significance": "pathogenic"}
        prompt = _is._build_variant_prompt(data)
        assert "variant" in prompt.lower()

    def test_with_user_genotype(self):
        data = {
            "rsid": "rs123",
            "user_genotype": "AA",
            "allele_string": "A/G",
        }
        prompt = _is._build_variant_prompt(data)
        assert "AA" in prompt

    def test_with_ref_homozygous_genotype(self):
        data = {
            "rsid": "rs456",
            "user_genotype": "GG",
            "allele_string": "G/A",
            "clinical_significance": "pathogenic",
        }
        prompt = _is._build_variant_prompt(data)
        assert "GG" in prompt


class TestGetLlmStatus:
    def test_returns_dict(self):
        status = _is.get_llm_status()
        assert isinstance(status, dict)
        assert "enabled" in status
        assert "provider" in status

    def test_provider_is_gemini(self):
        status = _is.get_llm_status()
        assert status["provider"] == "gemini"


class TestSetInsightsEnabled:
    def test_enable(self, tmp_path):
        f = tmp_path / ".state"
        with patch.object(_is, '_STATE_FILE', f):
            status = _is.set_insights_enabled(True)
            assert _is._insights_enabled is True
            assert f.read_text() == "1"

    def test_disable(self, tmp_path):
        f = tmp_path / ".state"
        with patch.object(_is, '_STATE_FILE', f):
            status = _is.set_insights_enabled(False)
            assert _is._insights_enabled is False
            assert f.read_text() == "0"

    def test_file_write_error_does_not_raise(self, tmp_path):
        mock_path = MagicMock()
        mock_path.write_text.side_effect = OSError("no perm")
        with patch.object(_is, '_STATE_FILE', mock_path):
            _is.set_insights_enabled(True)


class TestGenerateDashboardInsightDisabled:
    @pytest.mark.asyncio
    async def test_returns_disabled_when_off(self):
        orig = _is._insights_enabled
        _is._insights_enabled = False
        try:
            result = await _is.generate_insight("health", 1, {})
            assert result.get("disabled") is True
        finally:
            _is._insights_enabled = orig


class TestGenerateVariantInsightDisabled:
    @pytest.mark.asyncio
    async def test_returns_disabled_when_off(self):
        orig = _is._insights_enabled
        _is._insights_enabled = False
        try:
            result = await _is.generate_variant_insight("rs123", {})
            assert result.get("disabled") is True
        finally:
            _is._insights_enabled = orig

    @pytest.mark.asyncio
    async def test_returns_error_on_exception(self):
        orig = _is._insights_enabled
        _is._insights_enabled = True
        try:
            with patch.object(_is, '_call_llm', new=AsyncMock(side_effect=Exception("API down"))):
                result = await _is.generate_variant_insight("rs123", {})
                assert "error" in result
        finally:
            _is._insights_enabled = orig


# ──────────────────────────────────────────────
# variant_uploader
# ──────────────────────────────────────────────

class TestVariantUploader:
    def _make_session(self):
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_empty_variants_returns_zeros(self):
        from backend.services.variant_uploader import VariantUploader
        session = self._make_session()
        uploader = VariantUploader(session)
        result = await uploader.upload_variants(1, [])
        assert result == (0, 0)

    @pytest.mark.asyncio
    async def test_upload_variants_basic(self):
        from backend.services.variant_uploader import VariantUploader
        session = self._make_session()
        uploader = VariantUploader(session)
        with patch.object(uploader, '_process_variant_batch', new=AsyncMock(return_value=(1, 1))):
            result = await uploader.upload_variants(1, [{"rsid": "rs123", "alt_allele": "A"}])
            assert result[0] >= 0

    @pytest.mark.asyncio
    async def test_upload_calls_progress_callback(self):
        from backend.services.variant_uploader import VariantUploader
        session = self._make_session()
        uploader = VariantUploader(session)
        progress_calls = []

        async def on_progress(done, total):
            progress_calls.append((done, total))

        with patch.object(uploader, '_process_variant_batch', new=AsyncMock(return_value=(1, 0))):
            await uploader.upload_variants(1, [{"rsid": "rs1"}], on_progress=on_progress)
            assert len(progress_calls) > 0
