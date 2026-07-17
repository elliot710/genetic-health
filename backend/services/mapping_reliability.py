"""Reliability predicate for auto-discovered clinical variant mappings.

Single source of truth shared by auto-discovery (gate new mappings, U5) and
remediation (audit existing mappings, U6). A clinical mapping asserts that a
variant confers meaningful disease risk; it is unreliable when the underlying
ClinVar record is benign/conflicting, has a molecular consequence that does not
change the protein (synonymous, intron, UTR, …), or is a common allele — none
of which support a high-confidence personal-risk claim.
"""
from typing import Optional, Tuple

# Consequences that do not alter the protein product, so a "pathogenic" label on
# them is not a reliable basis for a personal-risk finding. Matched as substrings
# against a normalised (lowercased, spaces→underscores) consequence string.
_NON_DAMAGING_CONSEQUENCE_TOKENS = (
    'synonymous', 'intron', 'utr', 'non_coding', 'noncoding',
    'upstream', 'downstream', 'intergenic', 'regulatory', 'tf_binding',
)

# Consequences that DO alter the protein. molecular_consequence is a
# comma-separated list across transcripts; if any transcript carries a damaging
# consequence the variant is not "non-damaging", even when another transcript is
# intronic/UTR/synonymous. This prevents flagging a real missense/nonsense/splice
# variant that also has a benign annotation on an alternate transcript.
_DAMAGING_CONSEQUENCE_TOKENS = (
    'missense', 'nonsense', 'stop_gain', 'stop_lost', 'start_lost', 'frameshift',
    'splice', 'inframe', 'protein_altering', 'transcript_ablation',
    'transcript_amplification', 'coding_sequence', 'initiator_codon',
)

# A pathogenic rare-disease allele is rare; above this the allele is common.
_COMMON_AF_CEILING = 0.05

_BENIGN_PREFIXES = ('benign', 'likely_benign', 'likely benign')


def is_non_damaging_consequence(consequence: Optional[str]) -> bool:
    """True when a single molecular-consequence string is affirmatively
    non-damaging (synonymous/intron/UTR/… with no damaging term on any
    transcript). Unknown/empty consequence returns False (not disqualifying)."""
    cons = (consequence or '').strip().lower().replace(' ', '_')
    if not cons:
        return False
    has_damaging = any(t in cons for t in _DAMAGING_CONSEQUENCE_TOKENS)
    has_non_damaging = any(t in cons for t in _NON_DAMAGING_CONSEQUENCE_TOKENS)
    return has_non_damaging and not has_damaging


def is_reliable_clinical_mapping(
    clinical_significance: Optional[str],
    molecular_consequence: Optional[str],
    *frequencies: Optional[float],
) -> Tuple[bool, Optional[str]]:
    """Return ``(is_reliable, reason)``. ``reason`` is ``None`` when reliable,
    else a short human-readable disqualifier (used in the remediation report).

    Missing consequence or frequency is treated as *unknown*, not disqualifying —
    the runtime matching gate still guards those at analysis time.
    """
    # Missing significance is NOT a disqualifier on its own — a clinical mapping
    # may rest on non-ClinVar evidence (e.g. a rare LoF from gnomAD). Only an
    # affirmatively benign or conflicting classification disqualifies here; the
    # consequence and frequency checks below still catch weak-basis mappings.
    sig = (clinical_significance or '').strip().lower()
    if sig:
        if any(sig.startswith(p) for p in _BENIGN_PREFIXES):
            return False, f"benign significance ({clinical_significance})"
        if 'conflicting' in sig:
            return False, "conflicting classification"

    cons = (molecular_consequence or '').strip().lower().replace(' ', '_')
    if cons:
        has_damaging = any(t in cons for t in _DAMAGING_CONSEQUENCE_TOKENS)
        has_non_damaging = any(t in cons for t in _NON_DAMAGING_CONSEQUENCE_TOKENS)
        if has_non_damaging and not has_damaging:
            return False, f"non-damaging consequence ({molecular_consequence})"

    for af in frequencies:
        if isinstance(af, (int, float)) and not isinstance(af, bool) and af > _COMMON_AF_CEILING:
            return False, f"common allele (frequency {af:.0%})"

    return True, None
