"""Biological plausibility gating for clinical findings.

A defence-in-depth layer over allele-carriage verification. Carriage is
verified elsewhere; this module deliberately does not test it, so that a
regression in carriage verification cannot also disable this gate.

The 2026-09 incident reported an adult male as hemizygous-affected for Rett
syndrome and Duchenne muscular dystrophy. Both are lethal or grossly disabling
in childhood, so a living adult presenting them as new findings is incoherent
on its face. Nothing in the pipeline tested a finding against the existence of
the person reading it.
"""
from typing import Iterable, Optional

# Conditions that are lethal or grossly disabling in childhood. A living adult
# receiving one of these as a novel genetic finding is almost certainly looking
# at a false positive, not a diagnosis. Matched as lowercase substrings against
# the ClinVar condition name.
#
# Deliberately short and explicit: severity is not inferred from free text. The
# list only ESCALATES handling — it is never the sole gate, because an unlisted
# severe condition would otherwise sail through exactly as MECP2 did.
_SEVERE_EARLY_ONSET_PATTERNS = (
    'rett syndrome',
    'duchenne muscular dystrophy',
    'myotubular myopathy',
    'adrenoleukodystrophy',
    'orofaciodigital syndrome',
    'epileptic encephalopathy',
    'renpenning syndrome',
    'lissencephaly',
    'canavan disease',
    'tay-sachs',
    'spinal muscular atrophy, type i',
)

# ClinVar review statuses that represent corroborated assertions rather than a
# single unreviewed submission.
_STRONG_REVIEW_TOKENS = (
    'multiple submitters',
    'expert panel',
    'practice guideline',
)


def is_severe_early_onset(condition: Optional[str]) -> bool:
    """True when the condition is lethal or grossly disabling in childhood."""
    if not condition:
        return False
    text = condition.strip().lower()
    return any(pattern in text for pattern in _SEVERE_EARLY_ONSET_PATTERNS)


def has_strong_review(review_statuses: Optional[Iterable[str]]) -> bool:
    """True when ClinVar evidence is corroborated beyond a single submitter.

    Note this speaks only to confidence that the VARIANT is pathogenic. It says
    nothing about whether any particular person carries it.
    """
    if not review_statuses:
        return False
    return any(
        token in (status or '').lower()
        for status in review_statuses
        for token in _STRONG_REVIEW_TOKENS
    )


def is_corroborated(condition: Optional[str],
                    review_statuses: Optional[Iterable[str]],
                    is_low_confidence_call: bool) -> bool:
    """Whether an affected claim has evidence of the RIGHT KIND to stand.

    Review status corroborates that the variant is pathogenic. It says nothing
    about whether this person carries it, and carriage is the thing in doubt.

    A consumer-array I/D code reports only that an allele is longer or shorter
    than the reference. Resolving which one is the alternate (see
    rare_mutations._carries_clinvar_indel) establishes what the code *would*
    mean if the call were right; it does not make the call reliable. For a
    condition that is lethal or grossly disabling in childhood, being told a
    living adult is affected on that basis is not something a well-reviewed
    ClinVar record can rescue -- the record is about the variant, and the
    doubt is about the person.

    So for that combination no amount of review status corroborates, and the
    claim is reported as uncertain pending confirmatory testing.
    """
    if is_low_confidence_call and is_severe_early_onset(condition):
        return False
    return has_strong_review(review_statuses)


def requires_corroboration(condition: Optional[str], is_hemizygous_claim: bool) -> bool:
    """Whether an affected claim needs corroborating review status to stand.

    Two independent triggers, so an unlisted severe condition is still covered:
    membership of the curated severe list, or any hemizygous-affected claim —
    the shape that turned an ambiguous array code into eight diagnoses.
    """
    return bool(is_hemizygous_claim) or is_severe_early_onset(condition)
