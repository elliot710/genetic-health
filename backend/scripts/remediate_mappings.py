"""Audit and remediate existing auto-discovered CLINICAL variant mappings (U6).

Every auto-discovered clinical mapping (category health/carrier) is re-checked
against the same reliability predicate that now gates new mappings (U5), by
joining the mapping's rsid back to its ClinVar record for the molecular
consequence and allele frequency the mapping data does not itself store.
Unreliable mappings (benign/conflicting, non-damaging consequence, or common
allele) are soft-deactivated (is_active=False) with a recorded reason — never
hard-deleted, so an admin can re-review.

Usage (inside backend container):
  uv run python -m backend.scripts.remediate_mappings            # dry-run (report only)
  uv run python -m backend.scripts.remediate_mappings --apply    # deactivate unreliable
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from backend.db.database import async_session_factory
from backend.db.models import VariantMapping, ClinVarVariant
from backend.services.mapping_reliability import is_reliable_clinical_mapping

_CLINICAL_CATEGORIES = ("health", "carrier")


def evaluate_clinical_mapping(
    mapping_data: Dict[str, Any], clinvar_record: Optional[Any]
) -> Tuple[bool, Optional[str]]:
    """Reliability of one existing clinical mapping, joined to its ClinVar
    record (or None when the variant is no longer in ClinVar). Prefers the
    ClinVar record's significance/consequence/frequency; falls back to the
    mapping's own stored significance when no record is found."""
    data = mapping_data or {}
    sig = data.get("clinical_significance")
    consequence = None
    afs: Tuple[Optional[float], ...] = ()
    if clinvar_record is not None:
        sig = getattr(clinvar_record, "clinical_significance", None) or sig
        consequence = getattr(clinvar_record, "molecular_consequence", None)
        afs = (
            getattr(clinvar_record, "af_exac", None),
            getattr(clinvar_record, "af_tgp", None),
            getattr(clinvar_record, "af_esp", None),
        )
    return is_reliable_clinical_mapping(sig, consequence, *afs)


_CLINVAR_FIELDS = ("clinical_significance", "molecular_consequence", "af_exac", "af_tgp", "af_esp")


async def _load_clinvar_records(session, rsids: List[str]) -> List[Any]:
    if not rsids:
        return []
    return (await session.execute(
        select(ClinVarVariant).where(ClinVarVariant.rsid.in_(rsids))
    )).scalars().all()


def _merge_clinvar_records(records: List[Any]) -> Dict[str, Any]:
    """A variant may have several clinvar_variants rows (tsv + vcf); the VCF row
    carries molecular_consequence and the TSV row may carry others. Merge the
    first non-null value of each field across all rows for an rsid so the
    consequence/frequency signal is never lost to row order."""
    from types import SimpleNamespace
    merged: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        acc = merged.setdefault(rec.rsid, {f: None for f in _CLINVAR_FIELDS})
        for field in _CLINVAR_FIELDS:
            if acc[field] is None:
                acc[field] = getattr(rec, field, None)
    return {rsid: SimpleNamespace(**vals) for rsid, vals in merged.items()}


async def audit_clinical_mappings(session, *, apply: bool = False) -> Dict[str, Any]:
    """Audit (and optionally deactivate) auto-discovered clinical mappings."""
    rows = (await session.execute(
        select(VariantMapping).where(
            VariantMapping.category.in_(_CLINICAL_CATEGORIES),
            VariantMapping.map_type == "rsid",
            VariantMapping.is_auto_discovered.is_(True),
            VariantMapping.is_active.is_(True),
        )
    )).scalars().all()

    rsids = list({m.key for m in rows})
    clinvar_by_rsid: Dict[str, Any] = _merge_clinvar_records(
        await _load_clinvar_records(session, rsids)
    )

    unreliable: List[Dict[str, Any]] = []
    for mapping in rows:
        reliable, reason = evaluate_clinical_mapping(
            mapping.data, clinvar_by_rsid.get(mapping.key)
        )
        if reliable:
            continue
        unreliable.append({
            "rsid": mapping.key,
            "category": mapping.category,
            "condition": (mapping.data or {}).get("condition"),
            "reason": reason,
        })
        if apply:
            mapping.is_active = False
            mapping.data = {
                **(mapping.data or {}),
                "_deactivation_reason": reason,
                "_deactivated_at": datetime.now(timezone.utc).isoformat(),
            }
            flag_modified(mapping, "data")

    if apply and unreliable:
        await session.commit()

    return {
        "total": len(rows),
        "reliable": len(rows) - len(unreliable),
        "unreliable": len(unreliable),
        "applied": apply,
        "details": unreliable,
    }


async def main() -> None:
    apply = "--apply" in sys.argv
    async with async_session_factory() as session:
        report = await audit_clinical_mappings(session, apply=apply)

    mode = "APPLIED (deactivated)" if apply else "DRY-RUN (no changes)"
    print(f"\nClinical-mapping reliability audit — {mode}")
    print(f"  total auto-discovered clinical mappings: {report['total']}")
    print(f"  reliable:   {report['reliable']}")
    print(f"  unreliable: {report['unreliable']}")
    for row in report["details"]:
        print(f"    - {row['rsid']} [{row['category']}] {row['condition']!r}: {row['reason']}")


if __name__ == "__main__":
    asyncio.run(main())
