"""U2: dbSNP molecular-consequence cache — rsid → SO consequence terms.

The b151 GRCh37 dbSNP VCF encodes molecular consequence as boolean function-class
INFO flags (NSM/NSN/NSF/SYN/U3/U5/ASS/DSS/INT/R3/R5), not a single MC field, so
the loader maps those flags to Sequence Ontology terms.
"""
import os

from backend.services.annotation_sources.dbsnp_mc_cache import (
    build_dbsnp_mc_cache, DbsnpMcCache,
)

_VCF = """##fileformat=VCFv4.0
##INFO=<ID=RS,Number=1,Type=Integer,Description="dbSNP ID">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
1\t100\trs1\tT\tC\t.\t.\tRS=1;GENEINFO=X:1;NSM;ASP
1\t200\trs2\tG\tA\t.\t.\tRS=2;SYN
1\t300\trs3\tA\tT\t.\t.\tRS=3;INT;R5
1\t400\trs4\tC\tG\t.\t.\tRS=4;GENEINFO=Y:2
1\t500\trs5\tG\tGA\t.\t.\tRS=5;NSF;DSS
"""


def _write_vcf(dirpath) -> str:
    p = os.path.join(dirpath, "dbsnp.vcf")
    with open(p, "w") as fh:
        fh.write(_VCF)
    return p


class TestDbsnpMcCache:
    def _cache(self, tmp_path) -> DbsnpMcCache:
        db = str(tmp_path / "dbsnp.db")
        build_dbsnp_mc_cache(_write_vcf(str(tmp_path)), db)
        return DbsnpMcCache(db)

    def test_missense_flag_maps_to_so_term(self, tmp_path):
        assert self._cache(tmp_path).consequence_for_rsid("rs1") == ["missense_variant"]

    def test_synonymous_flag_maps_to_so_term(self, tmp_path):
        assert self._cache(tmp_path).consequence_for_rsid("rs2") == ["synonymous_variant"]

    def test_multiple_flags_return_multiple_terms(self, tmp_path):
        assert set(self._cache(tmp_path).consequence_for_rsid("rs3")) == {
            "intron_variant", "upstream_gene_variant",
        }

    def test_record_without_function_flag_has_no_consequence(self, tmp_path):
        assert self._cache(tmp_path).consequence_for_rsid("rs4") == []

    def test_frameshift_and_splice_flags(self, tmp_path):
        assert set(self._cache(tmp_path).consequence_for_rsid("rs5")) == {
            "frameshift_variant", "splice_donor_variant",
        }

    def test_unknown_rsid_returns_empty(self, tmp_path):
        assert self._cache(tmp_path).consequence_for_rsid("rs999") == []
