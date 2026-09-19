"""Duty-of-care re-run: report which stored verdicts changed under corrected logic.

Real users saw health-risk and drug-response verdicts produced by the pre-fix
insight logic. After the correctness fixes (U2-U7 on refactor/analysis-correctness)
some of those verdicts change. This tool re-generates verdicts for an analysis and
diffs them against what is currently stored, producing a per-analysis report of
MATERIAL changes (a risk level or drug response that flipped) so the operator can
decide who to notify and how.

Design: the diff/report core is pure and unit-tested against fixtures. The DB
re-run orchestration (`rerun_analysis`) delegates to the existing
`regenerate_insights` dispatcher, which persists the corrected verdicts — so
running this both fixes the analysis and reports what changed. It is an
out-of-band operator step (run per analysis, after a backup); it never notifies
users automatically — the report tells the operator whom to notify.

No PII in the report: it carries analysis_id, condition/gene/drug labels (reference
terms, not personal data), and old->new verdict strings. Never genotype/allele/rsid.
"""
import argparse
import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class VerdictChange:
    category: str          # 'health_risk' | 'drug_response'
    subject: str           # condition, or "GENE / drug" — reference label, not PII
    field: str             # 'risk_level' | 'pathogenicity' | 'response_type'
    before: Optional[str]
    after: Optional[str]


@dataclass(frozen=True)
class _HealthVerdict:
    condition: str
    risk_level: Optional[str]
    pathogenicity_classification: Optional[str] = None


@dataclass(frozen=True)
class _DrugVerdict:
    gene: str
    drug: str
    response_type: Optional[str]


def _health_verdicts(rows) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """Map condition -> (risk_level, pathogenicity_classification)."""
    return {
        r.condition: (r.risk_level, getattr(r, 'pathogenicity_classification', None))
        for r in rows
    }


def _drug_verdicts(rows) -> Dict[str, Optional[str]]:
    """Map "GENE / drug" -> response_type."""
    return {f"{r.gene} / {r.drug}": r.response_type for r in rows}


def diff_health_risks(before_rows, after_rows) -> List[VerdictChange]:
    before, after = _health_verdicts(before_rows), _health_verdicts(after_rows)
    changes: List[VerdictChange] = []
    for condition in sorted(before.keys() | after.keys()):
        b_level, b_path = before.get(condition, (None, None))
        a_level, a_path = after.get(condition, (None, None))
        if b_level != a_level:
            changes.append(VerdictChange('health_risk', condition, 'risk_level', b_level, a_level))
        if b_path != a_path:
            changes.append(VerdictChange('health_risk', condition, 'pathogenicity', b_path, a_path))
    return changes


def diff_drug_responses(before_rows, after_rows) -> List[VerdictChange]:
    before, after = _drug_verdicts(before_rows), _drug_verdicts(after_rows)
    changes: List[VerdictChange] = []
    for subject in sorted(before.keys() | after.keys()):
        b, a = before.get(subject), after.get(subject)
        if b != a:
            changes.append(VerdictChange('drug_response', subject, 'response_type', b, a))
    return changes


def diff_verdicts(before_health, after_health, before_drug, after_drug) -> List[VerdictChange]:
    """Full material-change list across both verdict categories."""
    return diff_health_risks(before_health, after_health) + \
        diff_drug_responses(before_drug, after_drug)


def has_material_change(changes: List[VerdictChange]) -> bool:
    return len(changes) > 0


def format_report(analysis_id: int, changes: List[VerdictChange]) -> str:
    """Human-readable, PII-free per-analysis report."""
    if not changes:
        return f"analysis {analysis_id}: no material change"
    lines = [f"analysis {analysis_id}: {len(changes)} material change(s)"]
    for c in changes:
        lines.append(f"  [{c.category}] {c.subject} · {c.field}: {c.before!r} -> {c.after!r}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Affected-analysis discovery
# ---------------------------------------------------------------------------

REASON_SEVERE_CLAIM = 'severe childhood-onset condition claimed as affected'
REASON_BARE_SYMBOL = 'gene symbol shown as the disease condition'
REASON_PHARMACOGENOMIC = 'drug-response entry listed as a rare disease'
REASON_BENIGN_ESCALATION = 'benign-classified variant above low risk'


@dataclass(frozen=True)
class AffectedAnalysis:
    analysis_id: int
    reasons: Tuple[str, ...]


def rare_mutation_reasons(row) -> List[str]:
    """Defect signatures visible on a stored RareMutation row."""
    from ..services.insight_generators.base import is_severe_early_onset
    from ..services.insight_generators.rare_mutations import (
        _is_bare_gene_symbol, _is_pharmacogenomic_condition,
    )

    condition = row.disease_association or ''
    gene = row.gene or ''
    reasons: List[str] = []
    if is_severe_early_onset(condition) and row.clinical_significance in (
            'pathogenic', 'likely_pathogenic'):
        reasons.append(REASON_SEVERE_CLAIM)
    if condition and _is_bare_gene_symbol(condition, {gene.strip().lower()}):
        reasons.append(REASON_BARE_SYMBOL)
    if condition and _is_pharmacogenomic_condition(condition):
        reasons.append(REASON_PHARMACOGENOMIC)
    return reasons


def health_risk_reasons(row) -> List[str]:
    """Defect signatures visible on a stored HealthRisk row."""
    classification = (row.pathogenicity_classification or '').lower()
    if classification in ('benign', 'likely_benign') and row.risk_level != 'low':
        return [REASON_BENIGN_ESCALATION]
    return []


def classify_affected(analysis_id: int, rare_rows, health_rows) -> Optional[AffectedAnalysis]:
    """None when nothing stored for this analysis matches a known defect."""
    reasons: List[str] = []
    for row in rare_rows:
        reasons.extend(rare_mutation_reasons(row))
    for row in health_rows:
        reasons.extend(health_risk_reasons(row))
    if not reasons:
        return None
    return AffectedAnalysis(analysis_id, tuple(sorted(set(reasons))))


def format_discovery_report(affected: List[AffectedAnalysis]) -> str:
    if not affected:
        return 'no affected analyses found'
    lines = [f'{len(affected)} affected analysis/analyses:']
    for item in affected:
        lines.append(f'  analysis {item.analysis_id}: ' + '; '.join(item.reasons))
    return '\n'.join(lines)


async def find_affected_analyses(session) -> List[AffectedAnalysis]:
    """Scan stored insight rows for the defect signatures this plan corrects."""
    from collections import defaultdict
    from sqlalchemy import select
    from ..db.models import HealthRisk, RareMutation

    rare_by_analysis = defaultdict(list)
    for row in (await session.execute(select(RareMutation))).scalars():
        rare_by_analysis[row.analysis_id].append(row)

    health_by_analysis = defaultdict(list)
    for row in (await session.execute(select(HealthRisk))).scalars():
        health_by_analysis[row.analysis_id].append(row)

    affected = []
    for analysis_id in sorted(rare_by_analysis.keys() | health_by_analysis.keys()):
        item = classify_affected(analysis_id, rare_by_analysis[analysis_id],
                                 health_by_analysis[analysis_id])
        if item:
            affected.append(item)
    return affected


async def _read_verdicts(session, analysis_id: int):
    """Snapshot stored health-risk and drug-response verdicts into plain, detached
    objects (so a later regeneration that deletes+replaces these rows can't mutate
    the captured 'before' state)."""
    from sqlalchemy import select
    from ..db.models import HealthRisk, DrugResponse

    health_rows = (await session.execute(
        select(HealthRisk).where(HealthRisk.analysis_id == analysis_id)
    )).scalars().all()
    drug_rows = (await session.execute(
        select(DrugResponse).where(DrugResponse.analysis_id == analysis_id)
    )).scalars().all()
    health = [_HealthVerdict(r.condition, r.risk_level,
                             getattr(r, 'pathogenicity_classification', None))
              for r in health_rows]
    drug = [_DrugVerdict(r.gene, r.drug, r.response_type) for r in drug_rows]
    return health, drug


async def rerun_analysis(analysis_id: int, user_id: Optional[int] = None):
    """Read stored verdicts, re-generate under the current (corrected) logic, and
    diff. Delegates the re-run to the existing `regenerate_insights` dispatcher,
    which rebuilds generator context from cached annotations and persists fresh
    verdict rows. The operator runs this OUT-OF-BAND, per analysis, after a backup.
    Returns (changes, report)."""
    from ..db.database import async_session_factory
    from ..services.insight_dispatcher import regenerate_insights

    async with async_session_factory() as session:
        before_health, before_drug = await _read_verdicts(session, analysis_id)

    await regenerate_insights(analysis_id, user_id)

    async with async_session_factory() as session:
        after_health, after_drug = await _read_verdicts(session, analysis_id)

    changes = diff_verdicts(before_health, after_health, before_drug, after_drug)
    return changes, format_report(analysis_id, changes)


async def _discover(explicit_ids: List[int]) -> List[AffectedAnalysis]:
    from ..db.database import async_session_factory

    async with async_session_factory() as session:
        affected = await find_affected_analyses(session)
    if explicit_ids:
        wanted = set(explicit_ids)
        affected = [a for a in affected if a.analysis_id in wanted]
    return affected


async def _run(explicit_ids: List[int], apply_changes: bool) -> None:
    affected = await _discover(explicit_ids)
    print(format_discovery_report(affected))
    if not apply_changes:
        print('\ndry run — nothing written. Re-run with --apply to regenerate.')
        return
    for item in affected:
        _, report = await rerun_analysis(item.analysis_id)
        print(report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('analysis_ids', type=int, nargs='*',
                        help='Limit to these analysis IDs. Omit to scan all analyses.')
    parser.add_argument('--apply', action='store_true',
                        help='Regenerate insights. Without it this only reports.')
    args = parser.parse_args()
    asyncio.run(_run(args.analysis_ids, args.apply))


if __name__ == '__main__':
    main()
