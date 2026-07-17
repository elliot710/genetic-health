"""SnpEff offline consequence cache (U4).

SnpEff is run OFFLINE, once, over the marker set as a commercial-safe (LGPL)
cross-check / fallback annotator. This module parses SnpEff's ANN field into an
rsid → consequence SQLite cache, preferring the MANE canonical transcript's
effect. The `run_snpeff` subprocess step is an ops/refresh action; the parser and
cache are pure and unit-tested.
"""
import os
import sqlite3
import subprocess
from typing import Dict, List, Optional

from backend.services.annotation_sources.vep_offline_cache import most_severe_consequence


def _effects_from_ann(ann_value: str, mane_cache) -> Dict[str, Optional[str]]:
    """From one record's ANN value → {'mane': cons|None, 'best': cons|None}."""
    result: Dict[str, Optional[str]] = {"mane": None, "best": None}
    for annotation in ann_value.split(","):
        fields = annotation.split("|")
        if len(fields) < 7:
            continue
        effect_field = fields[1]           # may be "a&b&c"
        feature_id = fields[6]             # transcript id
        row_cons = most_severe_consequence(effect_field.split("&"))
        if not row_cons:
            continue
        if mane_cache is not None and mane_cache.is_mane_transcript(feature_id):
            result["mane"] = most_severe_consequence([c for c in (result["mane"], row_cons) if c])
        result["best"] = most_severe_consequence([c for c in (result["best"], row_cons) if c])
    return result


def parse_snpeff_output(lines, mane_cache=None) -> Dict[str, str]:
    """Parse a SnpEff-annotated VCF → rsid → consequence."""
    out: Dict[str, str] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 8:
            continue
        rsid, info = cols[2], cols[7]
        if not rsid.startswith("rs"):
            continue
        ann = next((tok[4:] for tok in info.split(";") if tok.startswith("ANN=")), None)
        if not ann:
            continue
        picked = _effects_from_ann(ann, mane_cache)
        cons = picked["mane"] or picked["best"]
        if cons:
            out[rsid] = cons
    return out


def build_snpeff_cache(snpeff_vcf_path: str, db_path: str, mane_cache=None) -> int:
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(snpeff_vcf_path) as fh:
        resolved = parse_snpeff_output(fh, mane_cache=mane_cache)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS snpeff_consequence")
        conn.execute("CREATE TABLE snpeff_consequence (rsid TEXT PRIMARY KEY, consequence TEXT)")
        conn.executemany(
            "INSERT OR REPLACE INTO snpeff_consequence VALUES (?, ?)", resolved.items()
        )
        conn.commit()
        return len(resolved)
    finally:
        conn.close()


def run_snpeff(marker_vcf: str, snpeff_jar: str, genome: str, output_path: str) -> None:
    """Ops/refresh step: run SnpEff over the marker VCF. Not unit-tested
    (requires Java + the SnpEff genome db installed)."""
    with open(output_path, "w") as out:
        subprocess.run(
            ["java", "-jar", snpeff_jar, "-canon", genome, marker_vcf],
            check=True, stdout=out,
        )


class SnpEffConsequenceCache:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def consequence_for(self, rsid: Optional[str]) -> Optional[str]:
        if not rsid or not os.path.exists(self._db_path):
            return None
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT consequence FROM snpeff_consequence WHERE rsid = ?", (rsid,)
            ).fetchone()
        finally:
            conn.close()
        return row[0] if row else None
