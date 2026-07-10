"""Characterization snapshot of insight-generation behavior.

Captures the CURRENT output of the risk-assessment / zygosity / percentile
logic and of the health & cognitive generators, so that the correctness
fixes (U2-U7) can be proven as intentional deltas and any behavior-preserving
refactor is regression-checked.

The snapshot has two parts:

- ``functions``: direct output matrices for the pure decision helpers
  (``zygosity_adjust``, ``assess_drug_response``, ``assess_risk_level``,
  ``cognitive._adjust_percentile``). These are where the ref-allele-unknown
  and pathogenicity-score bugs live, and the generator loop skips the
  variants that would exercise them, so they are characterized directly.
- ``generators``: the rows each generator emits for a small fixture set,
  captured from the objects passed to ``session.add(...)``.

To regenerate the baseline after an intentional change:
    UPDATE_INSIGHT_SNAPSHOT=1 uv run pytest backend/tests/test_insight_snapshot.py -q
then review the git diff of snapshots/insight_snapshot.json to confirm the
deltas are the ones the change intended.
"""
import json
import os
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SNAPSHOT_PATH = pathlib.Path(__file__).parent / "snapshots" / "insight_snapshot.json"


# ── fixtures ────────────────────────────────────────────────────────────

class _Ann:
    """Minimal AnnotationResult stand-in — generators only read .annotation_data."""

    def __init__(self, data):
        self.annotation_data = data
        self.rsid = None
        self.was_reused = True
        self.source = "test"


def _variant(rsid, genotype, ref, alt="", chrom="1"):
    v = MagicMock()
    v.rsid = rsid
    v.genotype = genotype
    v.chromosome = chrom
    v.marker = MagicMock()
    v.marker.ref_allele = ref
    v.marker.alt_alleles = alt
    v.info = {}
    return v


class _FakeScorer:
    """Deterministic scorer so the snapshot isolates generator logic from the
    scoring engine (which the correctness fixes do not touch). Composite is
    read from a `_test_composite` sentinel embedded in the annotations dict."""

    def score_variant(self, annotations):
        comp = 0.0
        if isinstance(annotations, dict):
            comp = annotations.get("_test_composite", 0.0)
        if comp >= 0.80:
            cls = "pathogenic"
        elif comp >= 0.60:
            cls = "likely_pathogenic"
        elif comp >= 0.30:
            cls = "uncertain_significance"
        else:
            cls = "likely_benign"
        return {"composite_score": comp, "classification": cls, "evidence_count": 2}


def _ensembl_ann(allele_string, composite, clinvar_sig=None):
    annotations = {
        "ensembl": {"data": [{"allele_string": allele_string,
                              "most_severe_consequence": "missense_variant"}]},
        "_test_composite": composite,
    }
    if clinvar_sig is not None:
        annotations["clinvar_local"] = {
            "found": True,
            "clinical_significances": [clinvar_sig],
            "alt_allele": allele_string.split("/")[-1],
        }
    return _Ann({"annotations": annotations})


def _norm(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    return str(value)


def _capture_rows(added):
    rows = []
    for obj in added:
        fields = {k: _norm(v) for k, v in vars(obj).items() if not k.startswith("_")}
        rows.append({"table": type(obj).__name__, "fields": fields})
    rows.sort(key=lambda r: json.dumps(r, sort_keys=True))
    return rows


async def _run_generator(gen_func, variants, annotation_results, registry):
    from backend.services.insight_generators.base import (
        GeneratorContext, build_variant_profiles,
    )
    profiles = await build_variant_profiles(variants, annotation_results, {})
    added = []
    session = MagicMock()
    session.add = lambda o: added.append(o)
    session.flush = AsyncMock()
    ctx = GeneratorContext(
        analysis_id=1, variants=variants, annotation_results=annotation_results,
        session=session, rsid_gene_map={}, registry=registry,
        variant_profiles=profiles, inferred_sex="female",
    )
    await gen_func(ctx)
    return _capture_rows(added)


def _functions_snapshot():
    from backend.services.insight_generators.base import (
        zygosity_adjust, assess_drug_response, assess_risk_level,
    )
    from backend.services.insight_generators.cognitive import _adjust_percentile

    out = {}

    zy = []
    for level in ["moderate", "high", "low"]:
        for gt in ["A/G", "G/G", "A/A", "II", "DD", "--"]:
            for ref in ["A", None]:
                zy.append({"in": [level, gt, ref],
                           "out": zygosity_adjust(level, gt, ref_allele=ref)})
    out["zygosity_adjust"] = zy

    dr = []
    for gene in ["CYP2D6", "BRCA1"]:
        for gt in ["A/G", "G/G", "A/A", "--"]:
            for ref in ["A", None]:
                dr.append({"in": [gene, gt, ref],
                           "out": assess_drug_response(gt, gene, ref_allele=ref)})
    out["assess_drug_response"] = dr

    ar = []
    for mult in [1.5, 0.7, 2.5]:
        for comp in [None, 0.85, 0.5, 0.2]:
            ps = {"composite_score": comp} if comp is not None else None
            ar.append({"in": [mult, comp],
                       "out": assess_risk_level("A/G", mult, ref_allele="A",
                                                pathogenicity_score=ps)})
    out["assess_risk_level"] = ar

    cp = []
    for gt in ["A/G", "G/G", "A/A", "--"]:
        for ref in ["A", None]:
            cp.append({"in": [gt, ref], "out": _adjust_percentile(50, gt, ref)})
    out["cognitive_adjust_percentile"] = cp

    return out


async def _build_snapshot():
    from backend.services.insight_generators.health import generate_health_risks
    from backend.services.insight_generators.cognitive import generate_cognitive_profiles

    health_variants = [_variant("rs1001", "A/G", "A", "G")]
    health_ann = {"rs1001": _ensembl_ann("A/G", 0.85, clinvar_sig="Pathogenic")}
    health_registry = {"health": {"rsid": {"rs1001": {
        "condition": "Type 2 Diabetes", "risk_multiplier": 1.5,
        "gene": "TCF7L2", "recommendations": ["Maintain healthy weight"],
    }}, "gene": {}}}

    cog_variants = [_variant("rs1003", "A/G", "A", "G")]
    cog_ann = {"rs1003": _ensembl_ann("A/G", 0.40)}
    cog_registry = {"cognitive": {"rsid": {"rs1003": {
        "domain": "Memory", "score": 70, "percentile": 50,
        "suggestions": ["Do puzzles"],
    }}, "gene": {}}}

    return {
        "functions": _functions_snapshot(),
        "generators": {
            "health": await _run_generator(
                generate_health_risks, health_variants, health_ann, health_registry),
            "cognitive": await _run_generator(
                generate_cognitive_profiles, cog_variants, cog_ann, cog_registry),
        },
    }


@pytest.mark.asyncio
async def test_insight_characterization_snapshot():
    with patch("backend.services.scoring_engine.get_scoring_engine",
               return_value=_FakeScorer()), \
         patch("backend.services.insight_generators.base._bulk_load_gene_constraints",
               new=AsyncMock(return_value={})), \
         patch("backend.services.insight_generators.base._bulk_load_clinvar_gene_stats",
               new=AsyncMock(return_value={})):
        snapshot = await _build_snapshot()

    serialized = json.dumps(snapshot, indent=2, sort_keys=True)

    if os.environ.get("UPDATE_INSIGHT_SNAPSHOT") or not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.write_text(serialized + "\n")
        pytest.skip(f"Baseline snapshot written to {SNAPSHOT_PATH.name}")

    baseline = SNAPSHOT_PATH.read_text()
    assert serialized + "\n" == baseline, (
        "Insight output changed vs the characterization baseline. If intended, "
        "regenerate with UPDATE_INSIGHT_SNAPSHOT=1 and review the diff."
    )
