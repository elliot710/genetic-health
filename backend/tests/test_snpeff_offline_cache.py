"""U4: SnpEff offline consequence cache — parse the ANN field into rsid →
consequence, preferring the MANE canonical transcript's effect."""
import os

from backend.services.annotation_sources.snpeff_offline_cache import (
    parse_snpeff_output, build_snpeff_cache, SnpEffConsequenceCache,
)


class _FakeMane:
    def is_mane_transcript(self, tid):
        return tid == "ENST_MANE"


# SnpEff-annotated VCF. rs1: intron on an alt transcript + missense on the MANE
# transcript; rs2: synonymous; rs3: a compound effect (a&b) on one transcript.
_LINES = [
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
    "1\t100\trs1\tT\tC\t.\t.\tANN=C|intron_variant|MODIFIER|GENE1|ENSG1|transcript|ENST_ALT|,"
    "C|missense_variant|MODERATE|GENE1|ENSG1|transcript|ENST_MANE|",
    "1\t200\trs2\tG\tA\t.\t.\tANN=A|synonymous_variant|LOW|GENE2|ENSG2|transcript|ENST_X|",
    "1\t300\trs3\tA\tT\t.\t.\tANN=T|stop_gained&splice_region_variant|HIGH|GENE3|ENSG3|transcript|ENST_Y|",
]


class TestParseSnpeffOutput:
    def test_mane_effect_preferred(self):
        out = parse_snpeff_output(_LINES, mane_cache=_FakeMane())
        assert out["rs1"] == "missense_variant"

    def test_single_effect(self):
        out = parse_snpeff_output(_LINES, mane_cache=_FakeMane())
        assert out["rs2"] == "synonymous_variant"

    def test_compound_effect_takes_most_severe(self):
        out = parse_snpeff_output(_LINES, mane_cache=_FakeMane())
        assert out["rs3"] == "stop_gained"

    def test_no_mane_cache_uses_most_severe(self):
        out = parse_snpeff_output(_LINES, mane_cache=None)
        assert out["rs1"] == "missense_variant"


class TestSnpEffConsequenceCache:
    def test_build_and_lookup(self, tmp_path):
        p = os.path.join(str(tmp_path), "snpeff.vcf")
        with open(p, "w") as fh:
            fh.write("\n".join(_LINES) + "\n")
        db = str(tmp_path / "snpeff.db")
        build_snpeff_cache(p, db, mane_cache=_FakeMane())
        c = SnpEffConsequenceCache(db)
        assert c.consequence_for("rs2") == "synonymous_variant"
        assert c.consequence_for("rs999") is None
