"""Regression lock on the live Health card: "Acute lymphoid leukemia 28%".

Replays rs3820011 with its real Ensembl VEP record (read from the local VEP
cache, not invented): a multi-allelic missense in GNB1, absent from ClinVar,
scored 0.28 composite — i.e. likely benign. The live dashboard showed it as
"Acute lymphoid leukemia · Moderate Risk" while the same card's expanded view
said "Pathogenicity Score (likely benign) 28%", and the same variant produced
"Neurological Development · Low Risk" — identical evidence, different curated
multiplier.
"""
import asyncio
import json
import sqlite3
import zlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.services.insight_generators.base import GeneratorContext, VariantProfile, assess_risk_level
from backend.services.insight_generators.health import generate_health_risks

RSID, GENE, GENOTYPE = "rs3820011", "GNB1", "AC"
LIKELY_BENIGN = {"composite_score": 0.28, "classification": "likely_benign", "evidence_count": 3}
VEP_CACHE = Path("data_sources/ensembl/.vep_cache/vep_cache.db")

requires_vep_cache = pytest.mark.skipif(
    not VEP_CACHE.exists(), reason="local VEP cache not present"
)


def _real_vep_record():
    con = sqlite3.connect(f"file:{VEP_CACHE}?mode=ro", uri=True)
    row = con.execute("SELECT data FROM vep_data WHERE rsid=?", (RSID,)).fetchone()
    return json.loads(zlib.decompress(row[0])) if row else None


def _emit(condition, risk_multiplier):
    annotation = MagicMock()
    annotation.rsid = RSID
    annotation.annotation_data = {"annotations": {"ensembl": _real_vep_record()}}

    variant = MagicMock()
    variant.rsid, variant.genotype, variant.chromosome = RSID, GENOTYPE, "1"
    variant.marker = MagicMock()
    variant.marker.ref_allele, variant.marker.alt_alleles = "C", "A,G,T"

    profile = VariantProfile(
        rsid=RSID, genotype=GENOTYPE, effective_ref="C", gene=GENE,
        consequence="missense_variant", impact="MODERATE", chromosome="1",
        population_frequency=None, clinical_significance=None,
        is_benign=True, is_hom_ref=False, is_het=True, is_no_call=False,
        composite_score=0.28, pathogenicity_score=LIKELY_BENIGN,
        annotation_result=annotation, variant=variant,
    )
    emitted = []
    session = MagicMock()
    session.add = MagicMock(side_effect=lambda obj: emitted.append(obj))
    ctx = MagicMock(spec=GeneratorContext)
    ctx.analysis_id, ctx.variants = 1, [variant]
    ctx.annotation_results = {RSID: annotation}
    ctx.rsid_gene_map = {RSID: GENE}
    ctx.variant_profiles = {RSID: profile}
    ctx.inferred_sex, ctx.session = "male", session
    ctx.get_maps = MagicMock(return_value=({RSID: {
        "condition": condition, "gene": GENE, "risk_multiplier": risk_multiplier,
        "clinical_significance": "Pathogenic",
        "recommendations": ["Consult with healthcare provider"],
    }}, {}))
    asyncio.run(generate_health_risks(ctx))
    return emitted


@requires_vep_cache
class TestLiveLeukemiaCard:
    def test_likely_benign_variant_produces_no_clinical_health_finding(self):
        assert _emit("Acute lymphoid leukemia", 2.3) == []

    def test_the_low_risk_card_for_the_same_variant_is_also_gone(self):
        assert _emit("Neurological Development", 1.1) == []


class TestOneVariantCannotHaveTwoRiskLevels:
    """The curated multiplier was the only difference between the two cards."""

    def _level(self, multiplier):
        return assess_risk_level(GENOTYPE, multiplier, ref_allele="C",
                                 pathogenicity_score=LIKELY_BENIGN,
                                 population_frequency=None)

    def test_the_leukemia_multiplier_no_longer_reaches_moderate(self):
        assert self._level(2.3) == "low"

    def test_both_curated_multipliers_now_agree(self):
        assert self._level(2.3) == self._level(1.1)
