from typing import List

_Y_PRESENCE_THRESHOLD = 100
_MALE_X_HET_THRESHOLD = 0.05
_FEMALE_X_HET_THRESHOLD = 0.10

_HET_PAIRS = frozenset({
    'CT', 'TC', 'AG', 'GA', 'AC', 'CA',
    'GT', 'TG', 'AT', 'TA', 'CG', 'GC',
    'DI', 'ID',
})
_NO_CALL = frozenset({'--', '', 'NC', '00'})


def infer_biological_sex(variants: List) -> str:
    x_called = x_het = y_called = 0

    for variant in variants:
        chrom = getattr(variant, 'chromosome', None)
        genotype = getattr(variant, 'genotype', None)
        if not chrom or not genotype:
            continue

        gt = genotype.strip().upper()
        if gt in _NO_CALL:
            continue

        if chrom == 'Y':
            y_called += 1
        elif chrom == 'X':
            alleles = _parse_genotype_alleles(gt)
            if alleles is not None:
                x_called += 1
                if _is_heterozygous_pair(alleles):
                    x_het += 1

    return _classify_sex(x_called, x_het, y_called)


def _classify_sex(x_called: int, x_het: int, y_called: int) -> str:
    if x_called == 0:
        return 'unknown'

    x_het_rate = x_het / x_called
    has_y = y_called >= _Y_PRESENCE_THRESHOLD

    if has_y and x_het_rate < _MALE_X_HET_THRESHOLD:
        return 'male'
    if not has_y and x_het_rate >= _FEMALE_X_HET_THRESHOLD:
        return 'female'
    return 'unknown'


def _parse_genotype_alleles(gt: str):
    if gt in _NO_CALL:
        return None
    if '/' in gt:
        parts = gt.split('/')
        return parts if len(parts) == 2 else None
    if '|' in gt:
        parts = gt.split('|')
        return parts if len(parts) == 2 else None
    if len(gt) == 2:
        return [gt[0], gt[1]]
    return None


def _is_heterozygous_pair(alleles: List[str]) -> bool:
    if len(alleles) != 2:
        return False
    pair = alleles[0] + alleles[1]
    return pair in _HET_PAIRS or alleles[0] != alleles[1]
