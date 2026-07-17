"""U3: VEP offline consequence cache — parse VEP tab output into rsid →
consequence, choosing the MANE canonical transcript's consequence when present."""
import os

from backend.services.annotation_sources.vep_offline_cache import (
    parse_vep_output, build_vep_cache, VepConsequenceCache, most_severe_consequence,
)


class _FakeMane:
    """MANE stub: only ENST_MANE is canonical."""
    def is_mane_transcript(self, tid):
        return tid == "ENST_MANE"


# VEP default tab output: rs1 is missense on the MANE transcript but intron on an
# alternate transcript; rs2 is synonymous; rs3 has no MANE row.
_VEP_LINES = [
    "## VEP run",
    "#Uploaded_variation\tLocation\tAllele\tGene\tFeature\tFeature_type\tConsequence\tExtra",
    "rs1\t1:100\tC\tENSG1\tENST_ALT\tTranscript\tintron_variant\t-",
    "rs1\t1:100\tC\tENSG1\tENST_MANE\tTranscript\tmissense_variant\t-",
    "rs2\t1:200\tA\tENSG2\tENST_X\tTranscript\tsynonymous_variant\t-",
    "rs3\t1:300\tT\tENSG3\tENST_Y\tTranscript\tstop_gained,splice_region_variant\t-",
]


class TestMostSevere:
    def test_picks_most_severe(self):
        assert most_severe_consequence(["intron_variant", "missense_variant"]) == "missense_variant"
        assert most_severe_consequence(["synonymous_variant", "stop_gained"]) == "stop_gained"


class TestParseVepOutput:
    def test_mane_transcript_consequence_preferred(self):
        out = parse_vep_output(_VEP_LINES, mane_cache=_FakeMane())
        assert out["rs1"] == "missense_variant"  # MANE row, not the intron alt row

    def test_single_transcript_consequence(self):
        out = parse_vep_output(_VEP_LINES, mane_cache=_FakeMane())
        assert out["rs2"] == "synonymous_variant"

    def test_no_mane_row_falls_back_to_most_severe(self):
        out = parse_vep_output(_VEP_LINES, mane_cache=_FakeMane())
        assert out["rs3"] == "stop_gained"

    def test_no_mane_cache_uses_most_severe(self):
        out = parse_vep_output(_VEP_LINES, mane_cache=None)
        assert out["rs1"] == "missense_variant"  # most severe across rs1's rows


class TestVepConsequenceCache:
    def test_build_and_lookup(self, tmp_path):
        out_path = os.path.join(str(tmp_path), "vep.txt")
        with open(out_path, "w") as fh:
            fh.write("\n".join(_VEP_LINES) + "\n")
        db = str(tmp_path / "vep.db")
        build_vep_cache(out_path, db, mane_cache=_FakeMane())
        cache = VepConsequenceCache(db)
        assert cache.consequence_for("rs1") == "missense_variant"
        assert cache.consequence_for("rs999") is None
