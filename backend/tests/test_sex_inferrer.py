from types import SimpleNamespace
from backend.utils.sex_inferrer import (
    infer_biological_sex,
    _classify_sex,
    _parse_genotype_alleles,
    _is_heterozygous_pair,
)


def _make_variant(chromosome: str, genotype: str):
    return SimpleNamespace(chromosome=chromosome, genotype=genotype)


def _make_xy_variants():
    variants = []
    for _ in range(200):
        variants.append(_make_variant('Y', 'AA'))
    for _ in range(500):
        variants.append(_make_variant('X', 'GG'))
    for _ in range(3):
        variants.append(_make_variant('X', 'AG'))
    for _ in range(1000):
        variants.append(_make_variant('1', 'CC'))
    return variants


def _make_xx_variants():
    variants = []
    for _ in range(5):
        variants.append(_make_variant('Y', 'AA'))
    for _ in range(200):
        variants.append(_make_variant('X', 'GG'))
    for _ in range(50):
        variants.append(_make_variant('X', 'AG'))
    for _ in range(1000):
        variants.append(_make_variant('1', 'CC'))
    return variants


class TestInferBiologicalSex:
    def test_returns_male_for_xy_data(self):
        assert infer_biological_sex(_make_xy_variants()) == 'male'

    def test_returns_female_for_xx_data(self):
        assert infer_biological_sex(_make_xx_variants()) == 'female'

    def test_returns_unknown_for_empty(self):
        assert infer_biological_sex([]) == 'unknown'

    def test_returns_unknown_for_no_x_variants(self):
        variants = [_make_variant('1', 'AA')] * 100
        assert infer_biological_sex(variants) == 'unknown'

    def test_skips_no_call_genotypes(self):
        variants = [_make_variant('Y', '--')] * 200
        variants += [_make_variant('X', '--')] * 100
        assert infer_biological_sex(variants) == 'unknown'

    def test_skips_none_chromosome(self):
        variants = [SimpleNamespace(chromosome=None, genotype='AA')] * 100
        assert infer_biological_sex(variants) == 'unknown'

    def test_vcf_slash_format_male(self):
        variants = [_make_variant('Y', 'A/A')] * 200
        variants += [_make_variant('X', 'A/A')] * 500
        variants += [_make_variant('X', 'A/G')] * 2
        assert infer_biological_sex(variants) == 'male'

    def test_vcf_slash_format_female(self):
        variants = [_make_variant('Y', 'A/A')] * 2
        variants += [_make_variant('X', 'A/A')] * 200
        variants += [_make_variant('X', 'A/G')] * 60
        assert infer_biological_sex(variants) == 'female'

    def test_y_threshold_not_met_returns_unknown(self):
        variants = [_make_variant('Y', 'AA')] * 50
        variants += [_make_variant('X', 'GG')] * 500
        variants += [_make_variant('X', 'AG')] * 2
        assert infer_biological_sex(variants) == 'unknown'


class TestClassifySex:
    def test_male_signals(self):
        assert _classify_sex(x_called=1000, x_het=3, y_called=300) == 'male'

    def test_female_signals(self):
        assert _classify_sex(x_called=500, x_het=80, y_called=0) == 'female'

    def test_no_x_data_unknown(self):
        assert _classify_sex(x_called=0, x_het=0, y_called=200) == 'unknown'

    def test_y_present_but_high_x_het_unknown(self):
        assert _classify_sex(x_called=500, x_het=100, y_called=200) == 'unknown'

    def test_no_y_low_x_het_unknown(self):
        assert _classify_sex(x_called=500, x_het=5, y_called=0) == 'unknown'

    def test_boundary_y_threshold(self):
        assert _classify_sex(x_called=500, x_het=2, y_called=100) == 'male'
        assert _classify_sex(x_called=500, x_het=2, y_called=99) == 'unknown'

    def test_x_het_rate_boundary_male(self):
        assert _classify_sex(x_called=100, x_het=4, y_called=200) == 'male'
        assert _classify_sex(x_called=100, x_het=5, y_called=200) == 'unknown'

    def test_x_het_rate_boundary_female(self):
        assert _classify_sex(x_called=100, x_het=10, y_called=0) == 'female'
        assert _classify_sex(x_called=100, x_het=9, y_called=0) == 'unknown'


class TestParseGenotypeAlleles:
    def test_two_char_snp(self):
        assert _parse_genotype_alleles('AG') == ['A', 'G']

    def test_homozygous_snp(self):
        assert _parse_genotype_alleles('AA') == ['A', 'A']

    def test_vcf_slash(self):
        assert _parse_genotype_alleles('A/G') == ['A', 'G']

    def test_vcf_pipe(self):
        assert _parse_genotype_alleles('A|G') == ['A', 'G']

    def test_no_call_dash(self):
        assert _parse_genotype_alleles('--') is None

    def test_empty_string(self):
        assert _parse_genotype_alleles('') is None

    def test_indel_di(self):
        result = _parse_genotype_alleles('DI')
        assert result == ['D', 'I']

    def test_three_char_invalid(self):
        assert _parse_genotype_alleles('AGT') is None


class TestIsHeterozygousPair:
    def test_het_snp(self):
        assert _is_heterozygous_pair(['A', 'G']) is True

    def test_hom_snp(self):
        assert _is_heterozygous_pair(['A', 'A']) is False

    def test_indel_di(self):
        assert _is_heterozygous_pair(['D', 'I']) is True

    def test_indel_dd(self):
        assert _is_heterozygous_pair(['D', 'D']) is False

    def test_single_allele(self):
        assert _is_heterozygous_pair(['A']) is False
