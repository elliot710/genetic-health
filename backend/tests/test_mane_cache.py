"""U1: MANE Select canonical-transcript cache — gene → canonical transcript,
used to disambiguate multi-transcript consequences."""
import os

from backend.services.annotation_sources.mane_cache import build_mane_cache, ManeCache

_HEADER = (
    "#NCBI_GeneID\tEnsembl_Gene\tHGNC_ID\tsymbol\tname\tRefSeq_nuc\tRefSeq_prot\t"
    "Ensembl_nuc\tEnsembl_prot\tMANE_status\tGRCh38_chr\tchr_start\tchr_end\tchr_strand"
)
_ROWS = [
    # MANE Select — kept
    "GeneID:1\tENSG1\tHGNC:5\tA1BG\talpha-1-B\tNM_130786.4\tNP_570602.2\t"
    "ENST00000263100.8\tENSP1\tMANE Select\tNC_000019.10\t1\t2\t-",
    # MANE Plus Clinical — excluded (only MANE Select is canonical)
    "GeneID:2\tENSG2\tHGNC:6\tFOO\tfoo gene\tNM_000999.1\tNP_9\t"
    "ENST00000999.1\tENSP2\tMANE Plus Clinical\tNC_000001.11\t1\t2\t+",
]


def _write_summary(dirpath) -> str:
    p = os.path.join(dirpath, "mane.txt")
    with open(p, "w") as fh:
        fh.write(_HEADER + "\n" + "\n".join(_ROWS) + "\n")
    return p


class TestManeCache:
    def test_build_keeps_only_mane_select(self, tmp_path):
        n = build_mane_cache(_write_summary(str(tmp_path)), str(tmp_path / "mane.db"))
        assert n == 1

    def test_canonical_transcript_returns_refseq_and_ensembl(self, tmp_path):
        db = str(tmp_path / "mane.db")
        build_mane_cache(_write_summary(str(tmp_path)), db)
        t = ManeCache(db).canonical_transcript("A1BG")
        assert t["refseq"] == "NM_130786.4"
        assert t["ensembl"] == "ENST00000263100.8"

    def test_is_mane_transcript_matches_with_and_without_version(self, tmp_path):
        db = str(tmp_path / "mane.db")
        build_mane_cache(_write_summary(str(tmp_path)), db)
        c = ManeCache(db)
        assert c.is_mane_transcript("ENST00000263100.8") is True
        assert c.is_mane_transcript("ENST00000263100") is True  # versionless
        assert c.is_mane_transcript("NM_130786.4") is True

    def test_non_mane_select_transcript_is_not_matched(self, tmp_path):
        db = str(tmp_path / "mane.db")
        build_mane_cache(_write_summary(str(tmp_path)), db)
        assert ManeCache(db).is_mane_transcript("ENST00000999.1") is False

    def test_missing_gene_returns_none(self, tmp_path):
        db = str(tmp_path / "mane.db")
        build_mane_cache(_write_summary(str(tmp_path)), db)
        assert ManeCache(db).canonical_transcript("NOPE") is None
