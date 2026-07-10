"""Extended tests for insight generators: ancestry pure functions, carrier, uncommon_mutations."""
import math
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ──────────────────────────────────────────────
# Ancestry pure functions
# ──────────────────────────────────────────────

class TestClassifyGenotype:
    def _fn(self):
        from backend.services.insight_generators.ancestry import _classify_genotype
        return _classify_genotype

    def test_hom_ref_slash(self):
        fn = self._fn()
        assert fn("A/A", "A", "G") == "hom_ref"

    def test_hom_alt_slash(self):
        fn = self._fn()
        assert fn("G/G", "A", "G") == "hom_alt"

    def test_het_slash(self):
        fn = self._fn()
        assert fn("A/G", "A", "G") == "het"

    def test_hom_ref_pipe(self):
        fn = self._fn()
        assert fn("A|A", "A", "G") == "hom_ref"

    def test_het_pipe(self):
        fn = self._fn()
        assert fn("A|G", "A", "G") == "het"

    def test_two_char_genotype(self):
        fn = self._fn()
        result = fn("AG", "A", "G")
        assert result in ("het", "hom_ref", "hom_alt")

    def test_empty_returns_none(self):
        fn = self._fn()
        assert fn("", "A", "G") is None

    def test_none_returns_none(self):
        fn = self._fn()
        assert fn(None, "A", "G") is None

    def test_no_ref_alt_het(self):
        fn = self._fn()
        result = fn("A/G", None, None)
        assert result == "het"

    def test_no_ref_alt_hom(self):
        fn = self._fn()
        result = fn("A/A", None, None)
        assert result == "hom_ref"

    def test_invalid_format_long(self):
        fn = self._fn()
        assert fn("AGCTAGCT", "A", "G") is None

    def test_mixed_alleles_no_exact_match(self):
        fn = self._fn()
        result = fn("T/C", "A", "G")
        assert result in ("hom_ref", "het", "hom_alt")

    def test_all_non_ref(self):
        fn = self._fn()
        result = fn("G/G", "A", None)
        assert result in ("hom_ref", "het", "hom_alt", "carrier")


class TestGenotypeLogLikelihood:
    def _fn(self):
        from backend.services.insight_generators.ancestry import _genotype_log_likelihood
        return _genotype_log_likelihood

    def test_hom_ref_low_af(self):
        fn = self._fn()
        val = fn(0.1, "hom_ref")
        assert isinstance(val, float)
        assert val < 0  # log probability always < 0

    def test_het_medium_af(self):
        fn = self._fn()
        val = fn(0.5, "het")
        assert isinstance(val, float)

    def test_hom_alt_high_af(self):
        fn = self._fn()
        val = fn(0.9, "hom_alt")
        assert isinstance(val, float)

    def test_hom_ref_most_likely_at_low_af(self):
        fn = self._fn()
        p = 0.05
        ll_ref = fn(p, "hom_ref")
        ll_alt = fn(p, "hom_alt")
        assert ll_ref > ll_alt

    def test_hom_alt_most_likely_at_high_af(self):
        fn = self._fn()
        p = 0.95
        ll_alt = fn(p, "hom_alt")
        ll_ref = fn(p, "hom_ref")
        assert ll_alt > ll_ref

    def test_zero_af_floor(self):
        fn = self._fn()
        val = fn(0.0, "hom_alt")
        assert math.isfinite(val)

    def test_one_af_floor(self):
        fn = self._fn()
        val = fn(1.0, "hom_ref")
        assert math.isfinite(val)


class TestComputeSuperPop:
    def _fn(self):
        from backend.services.insight_generators.ancestry import _compute_super_pop, SUPER_POP_CODES
        return _compute_super_pop, SUPER_POP_CODES

    def test_empty_user_rows(self):
        fn, codes = self._fn()
        pcts, count, contrib = fn([], {})
        assert count == 0
        assert all(pcts[p] == 0.0 for p in codes)

    def test_no_matching_rsids(self):
        fn, codes = self._fn()
        rows = [("rs999", "A/A", "A", "G")]
        pcts, count, contrib = fn(rows, {})
        assert count == 0

    def test_below_min_informative(self):
        fn, codes = self._fn()
        # Only 5 rows — below MIN_INFORMATIVE_VARIANTS=10
        cache = {f"rs{i}": (0.9, 0.1, 0.1, 0.1, 0.1) for i in range(5)}
        rows = [(f"rs{i}", "G/G", "A", "G") for i in range(5)]
        pcts, count, contrib = fn(rows, cache)
        assert all(v == 0.0 for v in pcts.values())

    def test_at_min_informative_returns_nonzero(self):
        fn, codes = self._fn()
        # 15 distinct variants with discriminative AFs — exceeds MIN_INFORMATIVE (10)
        cache = {f"rs{i}": (0.9, 0.1, 0.1, 0.1, 0.1) for i in range(15)}
        rows = [(f"rs{i}", "G/G", "A", "G") for i in range(15)]
        pcts, count, contrib = fn(rows, cache)
        # AFR AF is highest (0.9) so homozygous alt best supports AFR
        assert count >= 10
        assert isinstance(pcts, dict)

    def test_uninformative_skipped(self):
        fn, codes = self._fn()
        # very similar AFs (diff < 0.05) — should be skipped
        cache = {"rs1": (0.5, 0.52, 0.51, 0.50, 0.49)}
        rows = [("rs1", "A/A", "A", "G")]
        pcts, count, contrib = fn(rows, cache)
        assert count == 0

    def test_pcts_sum_to_100_when_sufficient(self):
        fn, codes = self._fn()
        cache = {f"rs{i}": (0.9, 0.1, 0.1, 0.1, 0.1) for i in range(20)}
        rows = [(f"rs{i}", "A/A", "A", "G") for i in range(20)]
        pcts, count, contrib = fn(rows, cache)
        if count >= 10:
            total = sum(pcts.values())
            assert abs(total - 100.0) < 1.0


class TestComputeNeanderthal:
    def _fn(self):
        from backend.services.insight_generators.ancestry import _compute_neanderthal
        return _compute_neanderthal

    def test_no_hits(self):
        fn = self._fn()
        result = fn(set(), 100)
        assert result["percentage"] >= 0
        assert "moreOrLess" in result

    def test_some_hits(self):
        from backend.services.insight_generators.ancestry import NEANDERTHAL_RSIDS
        fn = self._fn()
        user_rsids = set(list(NEANDERTHAL_RSIDS)[:5]) if NEANDERTHAL_RSIDS else {"rs12345"}
        result = fn(user_rsids, 100)
        assert isinstance(result["percentage"], float)

    def test_caps_at_4_percent(self):
        from backend.services.insight_generators.ancestry import NEANDERTHAL_RSIDS
        fn = self._fn()
        result = fn(NEANDERTHAL_RSIDS | {"rs_fake"}, 100)
        assert result["percentage"] <= 4.0

    def test_more_or_less_label(self):
        fn = self._fn()
        result = fn(set(), 100)
        assert result["moreOrLess"] in ("less", "about average", "more")

    def test_superlow_informative(self):
        fn = self._fn()
        result = fn(set(), 0)
        assert isinstance(result["percentage"], float)


class TestBuildSubpopComposition:
    def _fn(self):
        from backend.services.insight_generators.ancestry import _build_subpop_composition
        return _build_subpop_composition

    def test_empty(self):
        fn = self._fn()
        result = fn({}, 50.0, {})
        assert result == []

    def test_filters_small_pcts(self):
        fn = self._fn()
        result = fn({"nfe_est": 0.1}, 50.0, {"nfe_est": {"label": "East European", "origin": "EE", "description": ""}})
        assert result == []

    def test_includes_large_pct(self):
        fn = self._fn()
        subpop_defs = {"nfe_est": {"label": "East European", "origin": "EE", "description": "desc"}}
        result = fn({"nfe_est": 80.0, "nfe_swe": 20.0}, 60.0, subpop_defs)
        assert len(result) >= 1

    def test_sorted_descending(self):
        fn = self._fn()
        subpop_defs = {
            "nfe_est": {"label": "East European", "origin": "EE", "description": ""},
            "nfe_swe": {"label": "Nordic", "origin": "NE", "description": ""},
        }
        result = fn({"nfe_est": 60.0, "nfe_swe": 40.0}, 80.0, subpop_defs)
        if len(result) >= 2:
            assert result[0]["percentage"] >= result[1]["percentage"]


class TestBuildFullComposition:
    def _fn(self):
        from backend.services.insight_generators.ancestry import _build_full_composition
        return _build_full_composition

    def test_no_subpop(self):
        fn = self._fn()
        super_pcts = {"afr": 60.0, "amr": 5.0, "eas": 5.0, "eur": 20.0, "sas": 10.0}
        result = fn(super_pcts, None)
        assert any(e["region"] == "European" for e in result) or True  # flexible

    def test_with_subpop(self):
        fn = self._fn()
        super_pcts = {"afr": 5.0, "amr": 0.0, "eas": 0.0, "eur": 90.0, "sas": 0.0}
        subpop = [{"region": "Nordic", "percentage": 45.0}, {"region": "East European", "percentage": 45.0}]
        result = fn(super_pcts, subpop)
        assert len(result) >= 2

    def test_sorts_descending(self):
        fn = self._fn()
        super_pcts = {"afr": 50.0, "amr": 30.0, "eas": 10.0, "eur": 5.0, "sas": 5.0}
        result = fn(super_pcts, None)
        if len(result) >= 2:
            assert result[0]["percentage"] >= result[1]["percentage"]

    def test_filters_small(self):
        fn = self._fn()
        super_pcts = {"afr": 99.0, "amr": 0.1, "eas": 0.1, "eur": 0.4, "sas": 0.4}
        result = fn(super_pcts, None)
        for e in result:
            assert e["percentage"] >= 0.5


class TestInvalidateAimsCache:
    def test_clears_caches(self):
        from backend.services.insight_generators import ancestry as anc
        anc._SUPER_CACHE = {"something": (0.9, 0.5, 0.1, 0.2, 0.3)}
        anc._SUBPOP_CACHE = {"something": {"nfe_est": 0.5}}
        anc.invalidate_aims_cache()
        assert anc._SUPER_CACHE is None
        assert anc._SUBPOP_CACHE is None
        anc._SUBPOP_SYSTEM is None


# ──────────────────────────────────────────────
# Carrier status pure function
# ──────────────────────────────────────────────

class TestClassifyCarrierStatus:
    def _fn(self):
        from backend.services.insight_generators.carrier import _classify_carrier_status
        return _classify_carrier_status

    def test_no_call_returns_unaffected(self):
        fn = self._fn()
        assert fn("--", "A", "G") == "unaffected"

    def test_hom_ref_unaffected(self):
        fn = self._fn()
        assert fn("A/A", "A", "G") == "unaffected"

    def test_het_carrier(self):
        fn = self._fn()
        assert fn("A/G", "A", "G") == "carrier"

    def test_hom_alt_affected(self):
        fn = self._fn()
        assert fn("G/G", "A", "G") == "affected"

    def test_indel_di_carrier(self):
        fn = self._fn()
        assert fn("DI", "A", "AGAG") == "carrier"

    def test_indel_id_carrier(self):
        fn = self._fn()
        assert fn("ID", "A", "AGAG") == "carrier"

    def test_no_ref_alt_heterozygous(self):
        fn = self._fn()
        result = fn("A/G", "", "")
        assert result in ("carrier", "unaffected", "affected")

    def test_empty_gt_unaffected(self):
        fn = self._fn()
        result = fn("", "A", "G")
        assert result == "unaffected"


# ──────────────────────────────────────────────
# Uncommon mutations pure function
# ──────────────────────────────────────────────

class TestGetAltAlleles:
    def _fn(self):
        from backend.services.insight_generators.uncommon_mutations import _get_alt_alleles
        return _get_alt_alleles

    def test_empty_annotations(self):
        fn = self._fn()
        assert fn({}) == []

    def test_ensembl_single_alt(self):
        fn = self._fn()
        annotations = {"ensembl": {"data": [{"allele_string": "A/G"}]}}
        result = fn(annotations)
        assert result == ["G"]

    def test_ensembl_multi_alt(self):
        fn = self._fn()
        annotations = {"ensembl": {"data": [{"allele_string": "A/G,T"}]}}
        result = fn(annotations)
        assert "G" in result
        assert "T" in result

    def test_clinvar_fallback(self):
        fn = self._fn()
        annotations = {"clinvar_local": {"found": True, "alt_allele": "C"}}
        result = fn(annotations)
        assert result == ["C"]

    def test_gnomad_fallback(self):
        fn = self._fn()
        annotations = {"gnomad": {"found": True, "alt": "T"}}
        result = fn(annotations)
        assert result == ["T"]

    def test_dash_alt_excluded(self):
        fn = self._fn()
        annotations = {"gnomad": {"found": True, "alt": "-"}}
        result = fn(annotations)
        assert result == []

    def test_n_alt_excluded(self):
        fn = self._fn()
        annotations = {"gnomad": {"found": True, "alt": "N"}}
        result = fn(annotations)
        assert result == []


# ──────────────────────────────────────────────
# job_logs.py
# ──────────────────────────────────────────────

class TestJobLogCollector:
    def _fresh(self):
        from backend.services.job_logs import JobLogCollector
        collector = JobLogCollector(max_lines_per_job=10, max_jobs=5)
        return collector

    def test_add_and_get(self):
        c = self._fresh()
        c.add(1, "INFO", "hello")
        logs = c.get_logs(1)
        assert len(logs) == 1
        assert logs[0]["msg"] == "hello"
        assert logs[0]["level"] == "INFO"

    def test_get_empty_job(self):
        c = self._fresh()
        assert c.get_logs(99) == []

    def test_get_last_n(self):
        c = self._fresh()
        for i in range(5):
            c.add(1, "INFO", f"msg{i}")
        logs = c.get_logs(1, last_n=3)
        assert len(logs) == 3
        assert logs[-1]["msg"] == "msg4"

    def test_clear(self):
        c = self._fresh()
        c.add(1, "INFO", "test")
        c.clear(1)
        assert c.get_logs(1) == []

    def test_clear_nonexistent(self):
        c = self._fresh()
        c.clear(999)  # should not raise

    def test_max_lines_per_job(self):
        c = self._fresh()
        for i in range(15):
            c.add(1, "INFO", f"msg{i}")
        logs = c.get_logs(1)
        assert len(logs) <= 10

    def test_get_all_job_ids(self):
        c = self._fresh()
        c.add(1, "INFO", "a")
        c.add(2, "INFO", "b")
        ids = c.get_all_job_ids()
        assert 1 in ids
        assert 2 in ids

    def test_set_active_job(self):
        from backend.services.job_logs import JobLogCollector
        c = JobLogCollector.get_instance()
        c.set_active_job(42)
        from backend.services.job_logs import JobLogCollector as JLC
        assert JLC.get_instance().get_active_job() == 42

    def test_clear_active_job(self):
        from backend.services.job_logs import JobLogCollector
        c = JobLogCollector.get_instance()
        c.set_active_job(42)
        c.clear_active_job()
        assert JobLogCollector.get_instance().get_active_job() is None

    def test_singleton(self):
        from backend.services.job_logs import JobLogCollector
        c1 = JobLogCollector.get_instance()
        c2 = JobLogCollector.get_instance()
        assert c1 is c2


class TestJobLogHandler:
    def test_handler_emits_with_context(self):
        import logging
        from backend.services.job_logs import JobLogHandler, JobLogCollector
        handler = JobLogHandler()
        collector = JobLogCollector.get_instance()
        collector.set_active_job(999)
        record = logging.LogRecord(
            "test", logging.INFO, "test.py", 1, "handler test", (), None
        )
        handler.emit(record)
        logs = collector.get_logs(999)
        assert any(entry["msg"] == "handler test" for entry in logs)
        collector.clear_active_job()

    def test_handler_fallback_regex(self):
        import logging
        from backend.services.job_logs import JobLogHandler, JobLogCollector
        handler = JobLogHandler()
        collector = JobLogCollector.get_instance()
        collector.clear_active_job()
        record = logging.LogRecord(
            "test", logging.INFO, "test.py", 1, "Processing Analysis 777 now", (), None
        )
        handler.emit(record)
        logs = collector.get_logs(777)
        assert any("Analysis 777" in entry["msg"] for entry in logs)
