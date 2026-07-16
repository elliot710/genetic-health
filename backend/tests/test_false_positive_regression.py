"""U12: end-to-end regression lock for the pathogenicity false-positive class.

Reverting the U2 matching-gate hard cap turns
test_common_pathogenic_alleles_produce_no_health_finding red — the test binds
the fix, not merely the current behaviour.
"""
import pytest

from backend.services.insight_generators.health import generate_health_risks
from backend.tests.fixtures.false_positive_variants import (
    FALSE_POSITIVE_SPECS, TRUE_POSITIVE_SPEC, build_health_ctx,
)


@pytest.mark.parametrize("spec", FALSE_POSITIVE_SPECS, ids=[s["desc"] for s in FALSE_POSITIVE_SPECS])
async def test_common_pathogenic_alleles_produce_no_health_finding(spec):
    result = await generate_health_risks(build_health_ctx(spec["rsid"], spec["af"]))
    assert result == 0


async def test_rare_pathogenic_allele_is_preserved():
    ctx = build_health_ctx(TRUE_POSITIVE_SPEC["rsid"], TRUE_POSITIVE_SPEC["af"])
    assert await generate_health_risks(ctx) >= 1
