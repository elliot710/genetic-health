from backend.services.gnomad.grch38_bridge import ensembl_grch38_variants


class TestEnsemblGrch38Variants:
    def test_biallelic_snp_maps_single_variant(self):
        result = ensembl_grch38_variants("rs1", "7", 100, "A/G")
        assert result == [("rs1", "7", 100, "A", "G")]

    def test_multiallelic_snp_maps_every_alt(self):
        result = ensembl_grch38_variants("rs2", "7", 100, "A/G/T")
        assert result == [("rs2", "7", 100, "A", "G"), ("rs2", "7", 100, "A", "T")]

    def test_deletion_shifts_position_back_one(self):
        result = ensembl_grch38_variants("rs3", "1", 200, "AT/-")
        assert result == [("rs3", "1", 199, "AT", "-")]

    def test_insertion_shifts_position_back_one(self):
        result = ensembl_grch38_variants("rs4", "1", 200, "-/AT")
        assert result == [("rs4", "1", 199, "-", "AT")]

    def test_strips_chr_prefix(self):
        result = ensembl_grch38_variants("rs5", "chr7", 100, "A/G")
        assert result == [("rs5", "7", 100, "A", "G")]

    def test_missing_position_returns_empty(self):
        assert ensembl_grch38_variants("rs6", "7", None, "A/G") == []

    def test_allele_string_without_alt_returns_empty(self):
        assert ensembl_grch38_variants("rs7", "7", 100, "A") == []
