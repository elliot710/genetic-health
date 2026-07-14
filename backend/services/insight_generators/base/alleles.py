"""
Allele parsing and genotype/zygosity classification helpers.
"""
from typing import Optional


# Strand complement translation table — shared by generators that verify a
# user's genotype against an annotation allele reported on the minus strand.
STRAND_COMPLEMENT = str.maketrans('ACGT', 'TGCA')


def get_ref_allele(variant) -> Optional[str]:
    """Extract the reference allele from the variant's marker."""
    marker = getattr(variant, 'marker', None)
    if marker:
        ref = getattr(marker, 'ref_allele', None)
        if ref and ref not in ('N', '-', '.', ''):
            return ref
    return None


def get_annotation_ref_allele(annotation_result) -> Optional[str]:
    """Extract the reference allele from annotation data (ClinVar local, Ensembl, gnomAD).

    More reliable than the marker's ref_allele for consumer CSV data where
    ref_allele == alt_alleles ~83% of the time.
    """
    if not annotation_result or not annotation_result.annotation_data:
        return None

    annotations = annotation_result.annotation_data.get('annotations', {})

    # ClinVar local — has explicit ref/alt alleles
    cv = annotations.get('clinvar_local', {})
    if cv and cv.get('found'):
        ref = cv.get('ref_allele') or cv.get('reference_allele')
        if ref and ref not in ('N', '-', '.', ''):
            return ref.strip().upper()

    # Ensembl VEP — allele_string format: "REF/ALT"
    ensembl = annotations.get('ensembl', {})
    data_list = ensembl.get('data', [])
    if data_list:
        allele_str = data_list[0].get('allele_string', '')
        if '/' in allele_str:
            ref = allele_str.split('/')[0].strip()
            if ref and ref not in ('N', '-', '.', ''):
                return ref.upper()

    # gnomAD — has ref column
    gnomad = annotations.get('gnomad', {})
    if gnomad and gnomad.get('found'):
        ref = gnomad.get('ref')
        if ref and ref not in ('N', '-', '.', ''):
            return ref.strip().upper()

    return None


def get_annotation_allele_parts(annotation_result) -> tuple:
    """Return (ref, alt) alleles from annotations, including '-' for indels.

    Unlike get_annotation_ref_allele(), this does NOT filter out '-' chars,
    so callers can distinguish insertion vs deletion variants for correct
    consumer D/I code interpretation.
    """
    if not annotation_result or not annotation_result.annotation_data:
        return (None, None)

    annotations = annotation_result.annotation_data.get('annotations', {})

    # Ensembl VEP — allele_string format: "REF/ALT" or "REF/ALT1,ALT2"
    # For multi-allelic sites (REF/ALT1,ALT2) we return ALL alts joined so
    # callers can check if the user carries ANY of the risk alleles at this
    # position, not just the arbitrarily-first one.
    ensembl = annotations.get('ensembl', {})
    data_list = ensembl.get('data', [])
    if data_list:
        allele_str = data_list[0].get('allele_string', '')
        if '/' in allele_str:
            parts = allele_str.split('/', 1)
            ref = parts[0].strip()
            alt = parts[1].strip()  # Keep full alt string, may be "A,T" for multi-allelic
            if ref and alt:
                return (ref.upper(), alt.upper())

    # gnomAD — has ref and alt columns (single alt)
    gnomad = annotations.get('gnomad', {})
    if gnomad and gnomad.get('found'):
        ref = gnomad.get('ref', '')
        alt = gnomad.get('alt', '')
        if ref and alt:
            return (ref.strip().upper(), alt.strip().upper())

    # ClinVar local — has explicit ref/alt alleles (single alt)
    cv = annotations.get('clinvar_local', {})
    if cv and cv.get('found'):
        ref = cv.get('ref_allele') or cv.get('reference_allele') or ''
        alt = cv.get('alt_allele') or cv.get('alternate_allele') or ''
        if ref and alt:
            return (ref.strip().upper(), alt.strip().upper())

    return (None, None)


def indel_d_is_ref(ref_allele: str | None, alt_allele: str | None) -> bool | None:
    """For consumer D/I indel codes, determine if D maps to the reference allele.

    D = shorter/deletion allele, I = longer/insertion allele.
    Returns True if D=ref (insertion variant), False if D=alt (deletion variant),
    None if we can't determine.
    """
    if not ref_allele or not alt_allele:
        return None
    # BUG-03: treat 'N' (unknown nucleotide placeholder from consumer CSVs)
    # the same as '-' / '.' — we cannot infer allele lengths from it.
    _UNKNOWN = ('-', '.', 'N')
    ref_up = ref_allele.strip().upper()
    alt_up = alt_allele.strip().upper()
    # For multi-allelic sites (e.g. "C,CCC" from allele_string "CC/C,CCC"),
    # use only the first alt allele for length comparison. This matches the
    # VariantDetailDialog.tsx frontend behaviour (alts[0]). Without this,
    # the full comma-joined string length is used, producing incorrect D/I
    # directionality for dual-allele consumer array variants (BUG-14).
    if ',' in alt_up:
        alt_up = alt_up.split(',')[0].strip()
    if ref_up in _UNKNOWN or alt_up in _UNKNOWN:
        return None
    ref_len = len(ref_up)
    alt_len = len(alt_up)
    if ref_len == alt_len:
        return None  # Not an indel or ambiguous
    return ref_len <= alt_len  # D = shorter allele; if ref is shorter, D=ref


def _get_effective_ref_allele(variant, annotation_result) -> Optional[str]:
    """Get the best available reference allele for a variant.

    Prefers annotation-derived ref (authoritative) over marker-derived ref.
    Discards marker ref when it equals marker alt (ambiguous consumer CSV data).
    """
    ann_ref = get_annotation_ref_allele(annotation_result)
    if ann_ref:
        return ann_ref

    marker = getattr(variant, 'marker', None)
    if not marker:
        return None
    marker_ref = getattr(marker, 'ref_allele', None)
    if not marker_ref or marker_ref in ('N', '-', '.', ''):
        return None
    # Don't trust marker ref if it equals alt (ambiguous consumer CSV)
    marker_alt = getattr(marker, 'alt_alleles', None) or ''
    if marker_ref.strip().upper() == marker_alt.strip().upper():
        return None
    return marker_ref.strip().upper()


def get_user_genotype(variant) -> Optional[str]:
    """Extract the user's genotype from the variant.

    Checks the dedicated ``genotype`` column first, then falls back to
    ``info.original_genotype`` (older CSV uploads stored it there).
    """
    gt = getattr(variant, 'genotype', None)
    if gt:
        return gt.strip().upper()
    info = getattr(variant, 'info', None)
    if isinstance(info, dict):
        og = info.get('original_genotype')
        if og:
            return str(og).strip().upper()
    return None


# Consumer array genotype codes for indels (insertions/deletions).
# These are NOT nucleotide alleles — they indicate structural variant status.
#   II = insertion/insertion = homozygous reference (user has the reference sequence)
#   DD = deletion/deletion = homozygous alternate (user carries the deletion)
#   DI or ID = heterozygous (one deleted copy, one reference copy)
#   -- = no call / failed genotyping
_INDEL_CODES = frozenset({'II', 'DD', 'DI', 'ID'})
_NO_CALL_CODES = frozenset({'--', '00', 'NC', './.', '.|.'})


def is_indel_genotype(genotype: Optional[str]) -> bool:
    """True when genotype uses consumer array indel codes (II/DD/DI/ID)."""
    if not genotype:
        return False
    return genotype.strip().upper() in _INDEL_CODES


def is_no_call_genotype(genotype: Optional[str]) -> bool:
    """True when genotype represents a failed or missing call."""
    if not genotype:
        return True
    gt = genotype.strip().upper()
    return gt in _NO_CALL_CODES or gt == ''


def _parse_alleles(genotype: Optional[str]):
    """Split a genotype string into a list of alleles, or return None.

    For hemizygous genotypes (single allele, e.g. X chromosome in males),
    returns a single-element list so callers can handle it.

    Consumer array indel codes (II, DD, DI, ID) are returned as-is
    since they are not nucleotide alleles.  Callers should use
    is_indel_genotype() to detect these before allele-level logic.
    """
    if not genotype:
        return None
    gt = genotype.strip().upper()
    # No-call or empty
    if gt in _NO_CALL_CODES or not gt:
        return None
    # Consumer array indel codes — return the code letters as "alleles"
    # so that II → ['I', 'I'], DD → ['D', 'D'], DI → ['D', 'I']
    if gt in _INDEL_CODES:
        return [gt[0], gt[1]]
    if '/' in gt:
        alleles = gt.split('/')
    elif '|' in gt:
        alleles = gt.split('|')
    elif len(gt) == 2:
        alleles = [gt[0], gt[1]]
    elif len(gt) == 1:
        return [gt]  # hemizygous (X chromosome, mitochondrial)
    else:
        return None
    return alleles if len(alleles) >= 1 else None


def is_homozygous_reference(genotype: Optional[str], ref_allele: Optional[str] = None,
                            alt_allele: Optional[str] = None) -> bool:
    """Return True when the user carries only the reference allele.

    Handles diploid (2 alleles) and hemizygous (1 allele, e.g. X chromosome in males).

    Consumer array indel codes (D=shorter, I=longer):
      For insertion variants (ref shorter than alt): DD=hom-ref, II=hom-alt
      For deletion variants (ref longer than alt):   II=hom-ref, DD=hom-alt
      DI/ID always = heterozygous

    When *alt_allele* is provided alongside *ref_allele*, the function uses
    allele length comparison to correctly interpret D/I codes.
    """
    if not genotype:
        return False
    gt = genotype.strip().upper()
    # No-call → not reference
    if gt in _NO_CALL_CODES:
        return False
    # Consumer array indel codes — use allele lengths when available
    if gt in _INDEL_CODES:
        d_ref = indel_d_is_ref(ref_allele, alt_allele)
        if d_ref is True:
            # Insertion variant: D=ref, I=alt
            return gt == 'DD'
        elif d_ref is False:
            # Deletion variant: I=ref, D=alt
            return gt == 'II'
        else:
            # Unknown allele lengths — can't determine, return False (conservative)
            return False
    alleles = _parse_alleles(genotype)
    if alleles is None:
        return False
    if ref_allele:
        ref = ref_allele.strip().upper()
        return all(a == ref for a in alleles)
    # Without ref_allele we cannot distinguish homozygous-reference from
    # homozygous-alternate.  Return False to avoid silently skipping
    # variants that might be homozygous for the risk allele.
    return False


def is_heterozygous(genotype: Optional[str]) -> bool:
    """Return True when the genotype has two different alleles.
    Hemizygous genotypes (1 allele) are never heterozygous."""
    if not genotype:
        return False
    gt = genotype.strip().upper()
    # Consumer array indel codes
    if gt in ('DI', 'ID'):
        return True   # one deletion, one insertion = het
    if gt in ('II', 'DD') or gt in _NO_CALL_CODES:
        return False
    alleles = _parse_alleles(genotype)
    if alleles is None or len(alleles) < 2:
        return False
    return alleles[0] != alleles[1]
