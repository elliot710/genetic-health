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


def test_seed_consequence_resolves_synonymous_from_dbsnp(tmp_path):
    """The seed rs397518480 (p.Ser115=) resolves to synonymous_variant from the
    dbSNP source — the consequence the health gate then drops. Binds the
    credibility fix to real source data, not a hand-set profile.consequence."""
    from backend.services.annotation_sources.dbsnp_mc_cache import (
        build_dbsnp_mc_cache, DbsnpMcCache,
    )
    from backend.services.annotation_sources.consequence_resolver import ConsequenceResolver

    vcf = tmp_path / "dbsnp.vcf"
    vcf.write_text(
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "X\t40597293\trs397518480\tC\tT\t.\t.\tRS=397518480;GENEINFO=ATP6AP2:10159;SYN\n"
    )
    db = str(tmp_path / "dbsnp.db")
    build_dbsnp_mc_cache(str(vcf), db)
    resolver = ConsequenceResolver(dbsnp=DbsnpMcCache(db))
    assert resolver.resolve("rs397518480") == "synonymous_variant"
