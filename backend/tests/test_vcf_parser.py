import pytest
import asyncio
from backend.utils.vcf_parser import VCFParser, RSID_PATTERN, VALID_CHROMOSOMES
from backend.core.exceptions import FileParsingException


@pytest.fixture
def parser():
    return VCFParser()


class TestNormalizeChromosome:
    def test_numeric_chromosome(self):
        assert VCFParser._normalize_chromosome("1") == "1"
        assert VCFParser._normalize_chromosome("22") == "22"

    def test_chr_prefix_stripped(self):
        assert VCFParser._normalize_chromosome("chr1") == "1"
        assert VCFParser._normalize_chromosome("chrX") == "X"

    def test_chr_prefix_lowercase(self):
        assert VCFParser._normalize_chromosome("chr22") == "22"

    def test_x_chromosome(self):
        assert VCFParser._normalize_chromosome("X") == "X"
        assert VCFParser._normalize_chromosome("23") == "X"
        assert VCFParser._normalize_chromosome("XX") == "X"
        assert VCFParser._normalize_chromosome("X_CHROMOSOME") == "X"

    def test_y_chromosome(self):
        assert VCFParser._normalize_chromosome("Y") == "Y"
        assert VCFParser._normalize_chromosome("24") == "Y"
        assert VCFParser._normalize_chromosome("XY") == "Y"
        assert VCFParser._normalize_chromosome("Y_CHROMOSOME") == "Y"

    def test_mitochondrial(self):
        assert VCFParser._normalize_chromosome("MT") == "MT"
        assert VCFParser._normalize_chromosome("25") == "MT"
        assert VCFParser._normalize_chromosome("M") == "MT"
        assert VCFParser._normalize_chromosome("MITOCHONDRIAL") == "MT"

    def test_invalid_chromosome_returns_none(self):
        assert VCFParser._normalize_chromosome("99") is None
        assert VCFParser._normalize_chromosome("Z") is None
        assert VCFParser._normalize_chromosome("chrUn") is None

    def test_quoted_chromosome(self):
        assert VCFParser._normalize_chromosome('"1"') == "1"

    def test_whitespace_stripped(self):
        assert VCFParser._normalize_chromosome(" 1 ") == "1"


class TestValidateVariant:
    def test_valid_variant(self, parser):
        variant = {
            "chromosome": "1",
            "position": 100000,
            "rsid": "rs12345",
            "id": "rs12345",
            "ref_allele": "A",
            "alt_allele": "T",
            "line_number": 1,
        }
        assert parser._validate_variant(variant) is True

    def test_invalid_chromosome(self, parser):
        variant = {
            "chromosome": "99",
            "position": 100000,
            "rsid": "rs12345",
            "id": "rs12345",
            "ref_allele": "A",
            "alt_allele": "T",
            "line_number": 1,
        }
        assert parser._validate_variant(variant) is False

    def test_position_too_low(self, parser):
        variant = {
            "chromosome": "1",
            "position": 0,
            "rsid": "rs12345",
            "id": "rs12345",
            "ref_allele": "A",
            "alt_allele": "T",
            "line_number": 1,
        }
        assert parser._validate_variant(variant) is False

    def test_position_too_high(self, parser):
        variant = {
            "chromosome": "1",
            "position": 400_000_000,
            "rsid": "rs12345",
            "id": "rs12345",
            "ref_allele": "A",
            "alt_allele": "T",
            "line_number": 1,
        }
        assert parser._validate_variant(variant) is False

    def test_invalid_rsid_cleared(self, parser):
        variant = {
            "chromosome": "1",
            "position": 100000,
            "rsid": "BADID123",
            "id": "BADID123",
            "ref_allele": "A",
            "alt_allele": "T",
            "line_number": 5,
        }
        result = parser._validate_variant(variant)
        assert result is True
        assert variant["rsid"] is None
        assert variant["id"].startswith("variant_")

    def test_placeholder_id_allowed(self, parser):
        variant = {
            "chromosome": "1",
            "position": 100000,
            "rsid": None,
            "id": "variant_1",
            "ref_allele": "A",
            "alt_allele": "T",
            "line_number": 1,
        }
        assert parser._validate_variant(variant) is True

    def test_invalid_allele_replaced_with_n(self, parser):
        variant = {
            "chromosome": "1",
            "position": 100000,
            "rsid": None,
            "id": "variant_1",
            "ref_allele": "Q",
            "alt_allele": "T",
            "line_number": 1,
        }
        parser._validate_variant(variant)
        assert variant["ref_allele"] == "N"


class TestParseInfoField:
    def test_empty_dot(self, parser):
        assert parser._parse_info_field(".") == {}

    def test_flag_field(self, parser):
        result = parser._parse_info_field("PASS")
        assert result["PASS"] is True

    def test_integer_value(self, parser):
        result = parser._parse_info_field("AC=5")
        assert result["AC"] == 5

    def test_float_value(self, parser):
        result = parser._parse_info_field("AF=0.05")
        assert result["AF"] == pytest.approx(0.05)

    def test_string_value(self, parser):
        result = parser._parse_info_field("Gene=BRCA1")
        assert result["Gene"] == "BRCA1"

    def test_multiple_fields(self, parser):
        result = parser._parse_info_field("AC=2;AN=100;AF=0.02")
        assert result["AC"] == 2
        assert result["AN"] == 100
        assert result["AF"] == pytest.approx(0.02)

    def test_mixed_flags_and_values(self, parser):
        result = parser._parse_info_field("SOMATIC;AC=3;PASS")
        assert result["SOMATIC"] is True
        assert result["AC"] == 3
        assert result["PASS"] is True


class TestParseVariantLine:
    def test_valid_vcf_line(self, parser):
        line = "1\t100000\trs12345\tA\tT\t.\tPASS\tAC=2"
        variant = parser._parse_variant_line(line, 0)
        assert variant is not None
        assert variant["chromosome"] == "1"
        assert variant["position"] == 100000
        assert variant["rsid"] == "rs12345"
        assert variant["ref_allele"] == "A"
        assert variant["alt_allele"] == "T"

    def test_too_few_fields_returns_none(self, parser):
        line = "1\t100000\trs12345\tA"
        assert parser._parse_variant_line(line, 0) is None

    def test_invalid_chromosome_returns_none(self, parser):
        line = "99\t100000\trs12345\tA\tT\t.\tPASS\t."
        assert parser._parse_variant_line(line, 0) is None

    def test_invalid_position_returns_none(self, parser):
        line = "1\tnotanint\trs12345\tA\tT\t.\tPASS\t."
        assert parser._parse_variant_line(line, 0) is None

    def test_dot_id_becomes_placeholder(self, parser):
        line = "1\t100000\t.\tA\tT\t.\tPASS\t."
        variant = parser._parse_variant_line(line, 0)
        assert variant is not None
        assert variant["rsid"] is None
        assert variant["id"].startswith("variant_")

    def test_chr_prefix_normalized(self, parser):
        line = "chr1\t100000\trs12345\tA\tT\t.\tPASS\t."
        variant = parser._parse_variant_line(line, 0)
        assert variant is not None
        assert variant["chromosome"] == "1"

    def test_quality_none_for_dot(self, parser):
        line = "1\t100000\trs12345\tA\tT\t.\tPASS\t."
        variant = parser._parse_variant_line(line, 0)
        assert variant is not None
        assert variant["quality"] is None

    def test_info_parsed(self, parser):
        line = "1\t100000\trs12345\tA\tT\t50\tPASS\tAC=2;AF=0.01"
        variant = parser._parse_variant_line(line, 0)
        assert variant is not None
        assert variant["info"]["AC"] == 2

    def test_vcf_genotype_het(self, parser):
        parser.sample_names = ["SAMPLE"]
        line = "1\t100000\trs12345\tA\tT\t50\tPASS\t.\tGT\t0/1"
        variant = parser._parse_variant_line(line, 0)
        assert variant is not None
        assert variant["genotype"] == "A/T"

    def test_vcf_genotype_hom_ref(self, parser):
        parser.sample_names = ["SAMPLE"]
        line = "1\t100000\trs12345\tA\tT\t50\tPASS\t.\tGT\t0/0"
        variant = parser._parse_variant_line(line, 0)
        assert variant["genotype"] == "A/A"

    def test_vcf_genotype_hom_alt(self, parser):
        parser.sample_names = ["SAMPLE"]
        line = "1\t100000\trs12345\tA\tT\t50\tPASS\t.\tGT\t1/1"
        variant = parser._parse_variant_line(line, 0)
        assert variant["genotype"] == "T/T"

    def test_vcf_genotype_phased(self, parser):
        parser.sample_names = ["SAMPLE"]
        line = "1\t100000\trs12345\tA\tT\t50\tPASS\t.\tGT\t0|1"
        variant = parser._parse_variant_line(line, 0)
        assert variant["genotype"] == "A/T"

    def test_vcf_genotype_no_call(self, parser):
        parser.sample_names = ["SAMPLE"]
        line = "1\t100000\trs12345\tA\tT\t50\tPASS\t.\tGT\t./."
        variant = parser._parse_variant_line(line, 0)
        assert variant["genotype"] is None

    def test_vcf_genotype_multiallelic(self, parser):
        parser.sample_names = ["SAMPLE"]
        line = "1\t100000\trs12345\tA\tT,C\t50\tPASS\t.\tGT\t1/2"
        variant = parser._parse_variant_line(line, 0)
        assert variant["genotype"] == "T/C"

    def test_vcf_genotype_with_extra_format_fields(self, parser):
        parser.sample_names = ["SAMPLE"]
        line = "1\t100000\trs12345\tA\tT\t50\tPASS\t.\tGT:DP:GQ\t0/1:30:99"
        variant = parser._parse_variant_line(line, 0)
        assert variant["genotype"] == "A/T"

    def test_vcf_no_sample_column_genotype_none(self, parser):
        line = "1\t100000\trs12345\tA\tT\t50\tPASS\t."
        variant = parser._parse_variant_line(line, 0)
        assert variant is not None
        assert variant.get("genotype") is None


class TestGtToNucleotides:
    def test_het(self, parser):
        assert parser._gt_to_nucleotides("0/1", "A", "T") == "A/T"

    def test_hom_ref(self, parser):
        assert parser._gt_to_nucleotides("0/0", "A", "T") == "A/A"

    def test_hom_alt(self, parser):
        assert parser._gt_to_nucleotides("1/1", "A", "T") == "T/T"

    def test_phased(self, parser):
        assert parser._gt_to_nucleotides("0|1", "G", "C") == "G/C"

    def test_no_call(self, parser):
        assert parser._gt_to_nucleotides("./.", "A", "T") is None

    def test_missing_gt(self, parser):
        assert parser._gt_to_nucleotides("", "A", "T") is None

    def test_multiallelic(self, parser):
        assert parser._gt_to_nucleotides("1/2", "A", "T,C") == "T/C"

    def test_alt_dot_hom_alt_maps_to_ref(self, parser):
        assert parser._gt_to_nucleotides("1/1", "A", ".") == "A/A"

    def test_alt_dot_het_maps_to_ref(self, parser):
        assert parser._gt_to_nucleotides("0/1", "G", ".") == "G/G"

    def test_multiallelic_with_dot(self, parser):
        assert parser._gt_to_nucleotides("1/2", "A", ".,T") == "A/T"


class TestParseCsvRow:
    def test_23andme_format(self, parser):
        row = {
            "rsid": "rs12345",
            "chromosome": "1",
            "position": "100000",
            "genotype": "AG",
        }
        variant = parser._parse_csv_row(row, 0)
        assert variant is not None
        assert variant["rsid"] == "rs12345"
        assert variant["chromosome"] == "1"
        assert variant["position"] == 100000

    def test_missing_chromosome_returns_none(self, parser):
        row = {
            "rsid": "rs12345",
            "position": "100000",
            "genotype": "AG",
        }
        assert parser._parse_csv_row(row, 0) is None

    def test_missing_position_returns_none(self, parser):
        row = {
            "rsid": "rs12345",
            "chromosome": "1",
            "genotype": "AG",
        }
        assert parser._parse_csv_row(row, 0) is None

    def test_allele1_allele2_combined(self, parser):
        row = {
            "rsid": "rs12345",
            "chromosome": "1",
            "position": "100000",
            "allele1": "A",
            "allele2": "G",
        }
        variant = parser._parse_csv_row(row, 0)
        assert variant is not None
        assert variant["genotype"] == "AG"

    def test_invalid_chromosome_skipped(self, parser):
        row = {
            "rsid": "rs12345",
            "chromosome": "99",
            "position": "100000",
            "genotype": "AG",
        }
        assert parser._parse_csv_row(row, 0) is None

    def test_no_call_genotype(self, parser):
        row = {
            "rsid": "rs12345",
            "chromosome": "1",
            "position": "100000",
            "genotype": "--",
        }
        variant = parser._parse_csv_row(row, 0)
        assert variant is None or variant.get("ref_allele") == "N"

    def test_slash_genotype_format(self, parser):
        row = {
            "rsid": "rs12345",
            "chromosome": "1",
            "position": "100000",
            "genotype": "A/G",
        }
        variant = parser._parse_csv_row(row, 0)
        assert variant is not None
        assert variant["ref_allele"] == "A"
        assert variant["alt_allele"] == "G"

    def test_rsid_without_rs_prefix_fixed(self, parser):
        row = {
            "rsid": "12345",
            "chromosome": "1",
            "position": "100000",
            "genotype": "AG",
        }
        variant = parser._parse_csv_row(row, 0)
        assert variant is not None
        assert variant["rsid"] == "rs12345"

    def test_case_insensitive_column_names(self, parser):
        row = {
            "RSID": "rs12345",
            "CHROMOSOME": "1",
            "POSITION": "100000",
            "GENOTYPE": "AG",
        }
        variant = parser._parse_csv_row(row, 0)
        assert variant is not None

    def test_scientific_notation_position(self, parser):
        row = {
            "rsid": "rs12345",
            "chromosome": "1",
            "position": "1e5",
            "genotype": "AG",
        }
        variant = parser._parse_csv_row(row, 0)
        assert variant is not None
        assert variant["position"] == 100000

    def test_chr_prefix_in_chromosome(self, parser):
        row = {
            "rsid": "rs12345",
            "chromosome": "chr1",
            "position": "100000",
            "genotype": "AG",
        }
        variant = parser._parse_csv_row(row, 0)
        assert variant is not None
        assert variant["chromosome"] == "1"


class TestGetVariantStatistics:
    @pytest.mark.asyncio
    async def test_empty_variants(self, parser):
        result = await parser.get_variant_statistics([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_snv_counting(self, parser):
        variants = [
            {"chromosome": "1", "position": 100, "ref_allele": "A", "alt_allele": "T", "quality": None},
            {"chromosome": "2", "position": 200, "ref_allele": "G", "alt_allele": "C", "quality": None},
        ]
        result = await parser.get_variant_statistics(variants)
        assert result["total_variants"] == 2
        assert result["variant_types"]["SNV"] == 2

    @pytest.mark.asyncio
    async def test_insertion_deletion_counting(self, parser):
        variants = [
            {"chromosome": "1", "position": 100, "ref_allele": "A", "alt_allele": "ATG", "quality": None},
            {"chromosome": "1", "position": 200, "ref_allele": "ATG", "alt_allele": "A", "quality": None},
        ]
        result = await parser.get_variant_statistics(variants)
        assert result["variant_types"]["Insertion"] == 1
        assert result["variant_types"]["Deletion"] == 1

    @pytest.mark.asyncio
    async def test_chromosome_distribution(self, parser):
        variants = [
            {"chromosome": "1", "position": 100, "ref_allele": "A", "alt_allele": "T", "quality": None},
            {"chromosome": "1", "position": 200, "ref_allele": "G", "alt_allele": "C", "quality": None},
            {"chromosome": "X", "position": 300, "ref_allele": "A", "alt_allele": "G", "quality": None},
        ]
        result = await parser.get_variant_statistics(variants)
        assert result["chromosomes"]["1"] == 2
        assert result["chromosomes"]["X"] == 1

    @pytest.mark.asyncio
    async def test_quality_statistics(self, parser):
        variants = [
            {"chromosome": "1", "position": 100, "ref_allele": "A", "alt_allele": "T", "quality": 50.0},
            {"chromosome": "1", "position": 200, "ref_allele": "G", "alt_allele": "C", "quality": 100.0},
        ]
        result = await parser.get_variant_statistics(variants)
        assert result["quality_stats"]["mean"] == 75.0
        assert result["quality_stats"]["min"] == 50.0
        assert result["quality_stats"]["max"] == 100.0

    @pytest.mark.asyncio
    async def test_no_quality_data(self, parser):
        variants = [
            {"chromosome": "1", "position": 100, "ref_allele": "A", "alt_allele": "T", "quality": None},
        ]
        result = await parser.get_variant_statistics(variants)
        assert result["quality_stats"] == {}


class TestFormatDetection:
    @pytest.mark.asyncio
    async def test_vcf_with_many_metadata_lines_uses_vcf_parser(self, parser):
        many_meta = "\n".join(f"##meta_{i}=value_{i}" for i in range(50))
        vcf_content = f"""{many_meta}
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE
1\t752721\trs3131972\tA\tC\t.\tPASS\t.\tGT\t0/1
1\t752918\trs200599638\tG\tT\t.\tPASS\t.\tGT\t1/1
""".encode()
        parser.sample_names = ["SAMPLE"]
        variants = await parser.parse_vcf_content(vcf_content)
        assert len(variants) == 2
        assert variants[0]["rsid"] == "rs3131972"
        assert variants[0]["genotype"] == "A/C"
        assert variants[1]["genotype"] == "T/T"

    @pytest.mark.asyncio
    async def test_vcf_with_info_commas_not_routed_to_csv(self, parser):
        vcf_content = b"""##fileformat=VCFv4.1
##INFO=<ID=CSQ,Number=.,Type=String,Description="multi,value,info">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE
1\t100000\trs12345\tA\tT\t.\tPASS\tCSQ=x,y,z\tGT\t0/1
"""
        parser.sample_names = ["SAMPLE"]
        variants = await parser.parse_vcf_content(vcf_content)
        assert len(variants) == 1
        assert variants[0]["genotype"] == "A/T"

    @pytest.mark.asyncio
    async def test_csv_without_vcf_header_uses_csv_parser(self, parser):
        csv_content = b"""rsid,chromosome,position,genotype
rs12345,1,100000,AG
rs67890,2,200000,CT
"""
        variants = await parser.parse_vcf_content(csv_content)
        assert len(variants) == 2
        assert variants[0]["rsid"] == "rs12345"


class TestParseFailureRaisesInsteadOfMocking:
    @pytest.mark.asyncio
    async def test_invalid_utf8_raises_file_parsing_exception(self, parser):
        invalid_utf8_content = b"\xff\xfe\x00\x01not valid utf-8"
        with pytest.raises(FileParsingException):
            await parser.parse_vcf_content(invalid_utf8_content)

    @pytest.mark.asyncio
    async def test_generate_mock_variants_no_longer_exists(self, parser):
        assert not hasattr(parser, "_generate_mock_variants")
