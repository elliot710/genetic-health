"""Golden-genome end-to-end regression harness.

Runs a fixed synthetic genome through the FULL insight-generator suite
(``ALL_GENERATORS``) and snapshots what each generator emits. Where the
per-generator characterization in ``test_insight_snapshot`` locks individual
decision helpers, this locks the whole insight surface for one stable input, so
any cross-stage drift — a change in variant-profile building, scoring, or any
single generator — shows up as a snapshot diff for the same genome.

Each generator runs against a shared deterministic scorer and a session mock
that returns empty query results, so the snapshot captures the registry-driven
insight logic without a live database. A generator that cannot run on the
fixture is recorded as ``{"raised": "<ExceptionType>"}`` — a stable marker, so a
refactor that flips a generator between working and raising is also caught.

To regenerate the baseline after an intentional change:
    UPDATE_GOLDEN_GENOME=1 uv run pytest backend/tests/test_golden_genome.py -q
then review the git diff of snapshots/golden_genome_snapshot.json.
"""
import json
import os
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SNAPSHOT_PATH = pathlib.Path(__file__).parent / "snapshots" / "golden_genome_snapshot.json"


class _FakeScorer:
    """Deterministic scorer — composite read from a `_test_composite` sentinel."""

    def score_variant(self, annotations):
        comp = annotations.get("_test_composite", 0.0) if isinstance(annotations, dict) else 0.0
        if comp >= 0.80:
            cls = "pathogenic"
        elif comp >= 0.60:
            cls = "likely_pathogenic"
        elif comp >= 0.30:
            cls = "uncertain_significance"
        else:
            cls = "likely_benign"
        return {"composite_score": comp, "classification": cls, "evidence_count": 2}


class _Ann:
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


def _ann(allele_string, composite, clinvar_sig=None):
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


def _empty_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    result.scalar.return_value = None
    result.scalar_one_or_none.return_value = None
    return result


def _mock_session():
    added = []
    session = MagicMock()
    session.add = lambda o: added.append(o)
    session.add_all = lambda objs: added.extend(objs)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock(return_value=_empty_result())
    return session, added


# ── The golden genome: a fixed set of variants + a registry spanning several
#    insight categories. Kept small and deterministic. ──────────────────────

def _golden_genome():
    variants = [
        _variant("rs1001", "A/G", "A", "G"),
        _variant("rs1002", "G/G", "A", "G"),
        _variant("rs1003", "A/G", "A", "G"),
        _variant("rs1004", "A/A", "C", "T", chrom="2"),
        _variant("rs1005", "C/T", "C", "T", chrom="7"),
    ]
    annotation_results = {
        "rs1001": _ann("A/G", 0.85, clinvar_sig="Pathogenic"),
        "rs1002": _ann("A/G", 0.65, clinvar_sig="Likely pathogenic"),
        "rs1003": _ann("A/G", 0.40),
        "rs1004": _ann("C/T", 0.20, clinvar_sig="Benign"),
        "rs1005": _ann("C/T", 0.90, clinvar_sig="Pathogenic"),
    }
    registry = {
        "health": {"rsid": {
            "rs1001": {"condition": "Type 2 Diabetes", "risk_multiplier": 1.5,
                       "gene": "TCF7L2", "recommendations": ["Maintain healthy weight"]},
            "rs1005": {"condition": "Hereditary Breast Cancer", "risk_multiplier": 2.5,
                       "gene": "BRCA1", "recommendations": ["Discuss screening"]},
        }, "gene": {}},
        "cognitive": {"rsid": {
            "rs1003": {"domain": "Memory", "score": 70, "percentile": 50,
                       "suggestions": ["Do puzzles"]},
        }, "gene": {}},
        "drug_response": {"rsid": {
            "rs1002": {"drug": "Warfarin", "gene": "VKORC1", "response": "sensitive",
                       "recommendations": ["Adjust dose"]},
        }, "gene": {}},
        "nutrition": {"rsid": {
            "rs1004": {"nutrient": "Folate", "gene": "MTHFR", "score": 60,
                       "recommendations": ["Leafy greens"]},
        }, "gene": {}},
    }
    return variants, annotation_results, registry


async def _run_all_generators():
    from backend.services.insight_generators import ALL_GENERATORS
    from backend.services.insight_generators.base import (
        GeneratorContext, build_variant_profiles,
    )

    variants, annotation_results, registry = _golden_genome()
    profiles = await build_variant_profiles(variants, annotation_results, {})

    out = {}
    for gen_name, gen_func in ALL_GENERATORS:
        session, added = _mock_session()
        ctx = GeneratorContext(
            analysis_id=1, variants=variants, annotation_results=annotation_results,
            session=session, rsid_gene_map={}, registry=registry,
            variant_profiles=profiles, inferred_sex="female",
        )
        try:
            await gen_func(ctx)
            out[gen_name] = _capture_rows(added)
        except Exception as exc:  # stable marker — see module docstring
            out[gen_name] = {"raised": type(exc).__name__}
    return out


@pytest.mark.asyncio
async def test_golden_genome_snapshot():
    with patch("backend.services.scoring_engine.get_scoring_engine",
               return_value=_FakeScorer()), \
         patch("backend.services.insight_generators.base._bulk_load_gene_constraints",
               new=AsyncMock(return_value={})), \
         patch("backend.services.insight_generators.base._bulk_load_clinvar_gene_stats",
               new=AsyncMock(return_value={})):
        snapshot = await _run_all_generators()

    serialized = json.dumps(snapshot, indent=2, sort_keys=True)

    if os.environ.get("UPDATE_GOLDEN_GENOME") or not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(serialized + "\n")
        pytest.skip(f"Baseline golden-genome snapshot written to {SNAPSHOT_PATH.name}")

    baseline = SNAPSHOT_PATH.read_text()
    assert serialized + "\n" == baseline, (
        "Golden-genome insight output changed vs baseline. If intended, "
        "regenerate with UPDATE_GOLDEN_GENOME=1 and review the diff."
    )
