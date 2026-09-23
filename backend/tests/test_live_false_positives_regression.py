"""Regression lock on the eight findings the owner actually saw.

DoD item 10 requires each of the eight originally-observed findings to be
checked by name. This file does that against their real ClinVar records.

A finding passes when the pipeline no longer presents it to a living adult
male as an established diagnosis — either it is dropped outright (carriage
does not verify) or it is reclassified as uncertain with the urgent clinical
flags cleared. Nothing here asserts the variant is benign; it asserts the app
does not claim this person is affected by it.
"""
import asyncio
from types import SimpleNamespace

import pytest

from backend.scripts.rerun_corrected_analyses import (
    REASON_SEVERE_CLAIM, classify_affected, rare_mutation_reasons,
)

from backend.services.insight_generators.rare_mutations import generate_rare_mutations
from backend.services.insight_generators.carrier import generate_carrier_status
from backend.tests.fixtures.live_false_positives import (
    LIVE_FALSE_POSITIVES, build_carrier_context, build_context,
)

SEVERE_CHILDHOOD_FINDINGS = [f for f in LIVE_FALSE_POSITIVES if f[1] != "F8"]


def _run(finding):
    ctx, emitted = build_context(*finding)
    asyncio.new_event_loop().run_until_complete(generate_rare_mutations(ctx))
    return emitted


def _ids(findings):
    return [f"{f[1]}/{f[0]}" for f in findings]


@pytest.mark.parametrize("finding", SEVERE_CHILDHOOD_FINDINGS, ids=_ids(SEVERE_CHILDHOOD_FINDINGS))
def test_severe_childhood_finding_is_not_presented_as_established(finding):
    emitted = _run(finding)
    assert all(row.clinical_significance not in ("pathogenic", "likely_pathogenic")
               for row in emitted)


@pytest.mark.parametrize("finding", SEVERE_CHILDHOOD_FINDINGS, ids=_ids(SEVERE_CHILDHOOD_FINDINGS))
def test_severe_childhood_finding_raises_no_urgent_counselling(finding):
    emitted = _run(finding)
    assert all(row.genetic_counseling_urgent is False for row in emitted)


@pytest.mark.parametrize("finding", SEVERE_CHILDHOOD_FINDINGS, ids=_ids(SEVERE_CHILDHOOD_FINDINGS))
def test_severe_childhood_finding_triggers_no_specialist_referral(finding):
    emitted = _run(finding)
    assert all(row.specialist_referral is False for row in emitted)


@pytest.mark.parametrize("finding", SEVERE_CHILDHOOD_FINDINGS, ids=_ids(SEVERE_CHILDHOOD_FINDINGS))
def test_carrier_panel_makes_no_affected_claim_either(finding):
    """The same finding reaches the Carrier panel, which reported six of these
    as 'affected' after the rare-mutations fix alone."""
    ctx, emitted = build_carrier_context(*finding)
    asyncio.new_event_loop().run_until_complete(generate_carrier_status(ctx))
    assert all(row.carrier_status != "affected" for row in emitted)


# ---------------------------------------------------------------------------
# U11 discovery must actually find these analyses, or --apply silently no-ops
# ---------------------------------------------------------------------------

def _stored_rare_row(gene, disease_association):
    """A row shaped the way the pre-fix pipeline wrote it."""
    return SimpleNamespace(gene=gene, disease_association=disease_association,
                           clinical_significance="pathogenic")


class TestDiscoveryFindsTheOwnersAnalysis:
    def test_every_severe_finding_is_flagged_for_regeneration(self):
        rows = [_stored_rare_row(f[1], f[0]) for f in SEVERE_CHILDHOOD_FINDINGS]
        assert all(rare_mutation_reasons(row) for row in rows)

    def test_a_joined_multi_condition_string_is_still_matched(self):
        """disease_association is '; '.join(conditions[:3]), so the severe name
        is often not the whole field."""
        row = _stored_rare_row(
            "MECP2", "Encephalopathy, neonatal severe; Rett syndrome; Intellectual disability")
        assert REASON_SEVERE_CLAIM in rare_mutation_reasons(row)

    def test_the_analysis_as_a_whole_is_flagged(self):
        rows = [_stored_rare_row(f[1], f[0]) for f in SEVERE_CHILDHOOD_FINDINGS]
        assert classify_affected(42, rows, []) is not None
