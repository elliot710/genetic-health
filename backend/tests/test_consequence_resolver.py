"""U5: unified consequence resolver — priority order over the offline caches,
used to fill consequence when the primary annotation lacks it."""
from backend.services.annotation_sources.consequence_resolver import ConsequenceResolver


class _Vep:
    def __init__(self, val): self.val = val
    def consequence_for(self, rsid): return self.val


class _SnpEff(_Vep):
    pass


class _Dbsnp:
    def __init__(self, terms): self.terms = terms
    def consequence_for_rsid(self, rsid): return list(self.terms)


class TestConsequenceResolver:
    def test_existing_consequence_wins(self):
        r = ConsequenceResolver(vep=_Vep("missense_variant"))
        assert r.resolve("rs1", existing_consequence="stop_gained") == "stop_gained"

    def test_vep_preferred_over_dbsnp_and_snpeff(self):
        r = ConsequenceResolver(
            vep=_Vep("missense_variant"),
            dbsnp=_Dbsnp(["synonymous_variant"]),
            snpeff=_SnpEff("intron_variant"),
        )
        assert r.resolve("rs1") == "missense_variant"

    def test_dbsnp_used_when_vep_absent(self):
        r = ConsequenceResolver(dbsnp=_Dbsnp(["synonymous_variant", "intron_variant"]))
        assert r.resolve("rs1") == "synonymous_variant"  # leading (most severe) term

    def test_snpeff_used_when_vep_and_dbsnp_miss(self):
        r = ConsequenceResolver(
            vep=_Vep(None), dbsnp=_Dbsnp([]), snpeff=_SnpEff("frameshift_variant"),
        )
        assert r.resolve("rs1") == "frameshift_variant"

    def test_all_miss_returns_none(self):
        r = ConsequenceResolver(vep=_Vep(None), dbsnp=_Dbsnp([]), snpeff=_SnpEff(None))
        assert r.resolve("rs1") is None

    def test_no_rsid_returns_none(self):
        r = ConsequenceResolver(dbsnp=_Dbsnp(["missense_variant"]))
        assert r.resolve(None) is None

    def test_no_caches_returns_none(self):
        assert ConsequenceResolver().resolve("rs1") is None
