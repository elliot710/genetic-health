from backend.scripts.rerun_corrected_analyses import (
    _DrugVerdict,
    _HealthVerdict,
    diff_verdicts,
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
