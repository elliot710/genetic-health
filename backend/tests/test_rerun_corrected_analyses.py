import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import backend.scripts.rerun_corrected_analyses as rerun_module
from backend.scripts.rerun_corrected_analyses import (
    REASON_BARE_SYMBOL,
    REASON_BENIGN_ESCALATION,
    REASON_PHARMACOGENOMIC,
    REASON_SEVERE_CLAIM,
    AffectedAnalysis,
    _DrugVerdict,
    _HealthVerdict,
    classify_affected,
    diff_verdicts,
    format_discovery_report,
    format_report,
    has_material_change,
)


def _health(condition, risk_level, pathogenicity=None):
    return _HealthVerdict(condition, risk_level, pathogenicity)


def _drug(gene, drug, response_type):
    return _DrugVerdict(gene, drug, response_type)


class TestDiffVerdicts:
    def test_risk_level_flip_is_reported(self):
        before = [_health('BRCA-related risk', 'high')]
        after = [_health('BRCA-related risk', 'moderate')]
        changes = diff_verdicts(before, after, [], [])
        assert [(c.subject, c.field, c.before, c.after) for c in changes] == [
            ('BRCA-related risk', 'risk_level', 'high', 'moderate')
        ]

    def test_pathogenicity_flip_is_reported(self):
        before = [_health('Condition X', 'moderate', 'likely_pathogenic')]
        after = [_health('Condition X', 'moderate', 'uncertain')]
        changes = diff_verdicts(before, after, [], [])
        assert [(c.field, c.before, c.after) for c in changes] == [
            ('pathogenicity', 'likely_pathogenic', 'uncertain')
        ]

    def test_drug_response_flip_is_reported(self):
        before = [_drug('CYP2D6', 'codeine', 'normal')]
        after = [_drug('CYP2D6', 'codeine', 'poor')]
        changes = diff_verdicts([], [], before, after)
        assert [(c.category, c.subject, c.before, c.after) for c in changes] == [
            ('drug_response', 'CYP2D6 / codeine', 'normal', 'poor')
        ]

    def test_identical_verdicts_report_no_change(self):
        health = [_health('Condition X', 'low', 'benign')]
        drug = [_drug('CYP2C19', 'clopidogrel', 'intermediate')]
        changes = diff_verdicts(health, list(health), drug, list(drug))
        assert changes == []
        assert has_material_change(changes) is False

    def test_added_verdict_is_reported_as_change(self):
        after = [_health('New finding', 'high')]
        changes = diff_verdicts([], after, [], [])
        assert changes[0].before is None and changes[0].after == 'high'


class TestFormatReport:
    def test_no_change_report_is_explicit(self):
        assert format_report(42, []) == "analysis 42: no material change"

    def test_change_report_lists_each_material_change_without_pii(self):
        changes = diff_verdicts(
            [_health('Condition X', 'high')], [_health('Condition X', 'low')], [], []
        )
        report = format_report(42, changes)
        assert "analysis 42: 1 material change(s)" in report
        assert "'high' -> 'low'" in report


# ---------------------------------------------------------------------------
# Affected-analysis discovery
# ---------------------------------------------------------------------------

def _rare(gene, condition, significance='pathogenic'):
    return SimpleNamespace(gene=gene, disease_association=condition,
                           clinical_significance=significance)


def _health_row(condition, risk_level, classification):
    return SimpleNamespace(condition=condition, risk_level=risk_level,
                           pathogenicity_classification=classification)


class TestDiscoveryFindsTheDefects:
    def test_severe_childhood_condition_claimed_as_affected_is_flagged(self):
        affected = classify_affected(1, [_rare('MECP2', 'Rett syndrome')], [])
        assert REASON_SEVERE_CLAIM in affected.reasons

    def test_gene_symbol_shown_as_a_condition_is_flagged(self):
        affected = classify_affected(1, [_rare('POLD2', 'Pold2')], [])
        assert REASON_BARE_SYMBOL in affected.reasons

    def test_drug_response_listed_as_a_rare_disease_is_flagged(self):
        affected = classify_affected(1, [_rare('CYP2D6', 'Tramadol response')], [])
        assert REASON_PHARMACOGENOMIC in affected.reasons

    def test_benign_variant_above_low_risk_is_flagged(self):
        affected = classify_affected(
            1, [], [_health_row('Acute lymphoid leukemia', 'moderate', 'likely_benign')]
        )
        assert REASON_BENIGN_ESCALATION in affected.reasons

    def test_each_reason_is_listed_once_however_many_rows_carry_it(self):
        rows = [_rare('MECP2', 'Rett syndrome'), _rare('DMD', 'Duchenne muscular dystrophy')]
        assert classify_affected(1, rows, []).reasons == (REASON_SEVERE_CLAIM,)


class TestDiscoveryLeavesSoundAnalysesAlone:
    def test_an_analysis_with_no_defect_signature_is_not_flagged(self):
        rare = [_rare('BRCA2', 'Hereditary breast and ovarian cancer')]
        health = [_health_row('Type 2 diabetes', 'low', 'likely_benign')]
        assert classify_affected(1, rare, health) is None

    def test_a_severe_condition_not_claimed_as_pathogenic_is_not_flagged(self):
        rare = [_rare('MECP2', 'Rett syndrome', significance='uncertain')]
        assert classify_affected(1, rare, []) is None

    def test_an_analysis_with_nothing_stored_is_not_flagged(self):
        assert classify_affected(1, [], []) is None


class TestDiscoveryReport:
    def test_empty_scan_says_so_rather_than_printing_nothing(self):
        assert format_discovery_report([]) == 'no affected analyses found'

    def test_report_names_each_affected_analysis(self):
        affected = [classify_affected(42, [_rare('POLD2', 'Pold2')], [])]
        assert 'analysis 42' in format_discovery_report(affected)


class TestDryRunIsTheDefault:
    def test_dry_run_reports_without_regenerating(self):
        affected = [AffectedAnalysis(42, (REASON_BARE_SYMBOL,))]
        regenerated = []
        with patch.object(rerun_module, '_discover', AsyncMock(return_value=affected)), \
             patch.object(rerun_module, 'rerun_analysis',
                          AsyncMock(side_effect=lambda aid: regenerated.append(aid))):
            asyncio.run(rerun_module._run([], apply_changes=False))
        assert regenerated == []

    def test_apply_regenerates_every_affected_analysis(self):
        affected = [AffectedAnalysis(42, (REASON_BARE_SYMBOL,)),
                    AffectedAnalysis(43, (REASON_SEVERE_CLAIM,))]
        regenerated = []

        async def _fake_rerun(analysis_id):
            regenerated.append(analysis_id)
            return [], ''

        with patch.object(rerun_module, '_discover', AsyncMock(return_value=affected)), \
             patch.object(rerun_module, 'rerun_analysis', _fake_rerun):
            asyncio.run(rerun_module._run([], apply_changes=True))
        assert regenerated == [42, 43]
