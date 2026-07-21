from __future__ import annotations

from typing import List, Optional, Tuple

# GRCh37↔GRCh38 bridge: user uploads and the gnomAD v2 AF store are GRCh37, but
# the gnomAD CADD TSVs are GRCh38. Rather than a chain-file liftover, we reuse
# the GRCh38 coordinates Ensembl VEP already resolved per rsid as the position
# map. This is the single source of that translation — both the cache builder
# and the per-analysis tabix fallback expand Ensembl records through here so the
# two paths cannot drift (e.g. on multi-allelic handling).


def ensembl_grch38_variants(
    rsid: str,
    chrom: Optional[str],
    pos: Optional[int],
    allele_string: Optional[str],
) -> List[Tuple[str, str, int, str, str]]:
    """Expand one Ensembl VEP GRCh38 record into VCF-style variant tuples.

    Returns [(rsid, chrom, vcf_pos, ref, alt), ...] — one per alternate allele,
    so multi-allelic sites map every alt. Returns [] when the record lacks the
    coordinates or an alternate allele needed for a gnomAD tabix lookup.
    """
    if not chrom or not pos or not allele_string:
        return []
    parts = allele_string.split("/")
    if len(parts) < 2:
        return []
    ref = parts[0].strip()
    alts = [a.strip() for part in parts[1:] for a in part.split(",") if a.strip()]
    if not alts:
        return []
    chrom_clean = str(chrom).replace("chr", "").strip()
    # Ensembl reports indels 1-based on the affected base; the gnomAD VCF anchors
    # them one position earlier. Shift the whole site when any allele is a dash.
    is_indel = ref == "-" or any(alt == "-" for alt in alts)
    vcf_pos = int(pos) - 1 if is_indel else int(pos)
    return [(rsid, chrom_clean, vcf_pos, ref, alt) for alt in alts]
