"""A single-base array call cannot verify carriage of a multi-base ClinVar allele.

The live record behind this is rs267608520 (MECP2, Rett syndrome): ClinVar
describes ref=ATCACCAT alt=CAC, an 8bp complex indel, while the consumer array
reports a one-base genotype. Neither the I/D branch nor the single-base
nucleotide branch of the carriage check covered that pair, so the finding
reached the X-linked branch unverified and "not heterozygous" became a
diagnosis — the same ordering failure as the 2026-09-16 incident, in a shape
the first fix did not model.
"""
import pytest

from backend.services.insight_generators.rare_mutations import generate_rare_mutations
from backend.tests.fixtures.live_false_positives import build_context

MECP2_COMPLEX_INDEL = dict(
    condition="Rett syndrome", gene="MECP2", rsid="rs267608520",
    ref="ATCACCAT", alt="CAC",
    review_status="criteria provided, multiple submitters, no conflicts",
)


def _female_context(genotype):
    ctx, emitted = build_context(genotype=genotype, **MECP2_COMPLEX_INDEL)
    ctx.inferred_sex = "female"
    return ctx, emitted


@pytest.mark.asyncio
async def test_single_base_genotype_makes_no_claim_against_multibase_clinvar_alt():
    ctx, emitted = _female_context("AA")

    await generate_rare_mutations(ctx)

    assert emitted == []


@pytest.mark.asyncio
async def test_single_base_genotype_makes_no_claim_against_multibase_clinvar_ref():
    ctx, emitted = build_context(
        condition="Rett syndrome", gene="MECP2", rsid="rs267608520",
        ref="AT", alt="A", genotype="AA",
        review_status="criteria provided, multiple submitters, no conflicts",
    )

    await generate_rare_mutations(ctx)

    assert emitted == []


@pytest.mark.asyncio
async def test_true_snv_carriage_is_still_reported():
    ctx, emitted = build_context(
        condition="Rett syndrome", gene="MECP2", rsid="rs267608520",
        ref="T", alt="C", genotype="CC",
        review_status="criteria provided, multiple submitters, no conflicts",
    )

    await generate_rare_mutations(ctx)

    assert len(emitted) == 1


def _carrier_context(genotype, ref, alt):
    from backend.tests.fixtures.live_false_positives import build_carrier_context

    ctx, emitted = build_carrier_context(
        "Rett syndrome", "MECP2", "rs267608520", genotype, ref, alt,
        "criteria provided, multiple submitters, no conflicts",
    )
    ctx.inferred_sex = "female"
    return ctx, emitted


@pytest.mark.asyncio
async def test_carrier_makes_no_claim_against_multibase_clinvar_ref():
    from backend.services.insight_generators.carrier import generate_carrier_status

    ctx, emitted = _carrier_context("AA", "AT", "A")

    await generate_carrier_status(ctx)

    assert emitted == []


@pytest.mark.asyncio
async def test_carrier_still_reports_a_true_snv_homozygote():
    from backend.services.insight_generators.carrier import generate_carrier_status

    ctx, emitted = _carrier_context("CC", "T", "C")

    await generate_carrier_status(ctx)

    assert emitted[0].carrier_status == "affected"
