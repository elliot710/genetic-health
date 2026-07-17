"""VEP offline consequence cache (U3).

VEP is run OFFLINE, once, over the fixed consumer-array marker set (not per
analysis). This module parses VEP's tab output into an rsid → consequence SQLite
cache, choosing the MANE canonical transcript's consequence when available so a
variant is not mislabelled by an alternate transcript. The `run_vep` subprocess
step is an ops/refresh action (see backend/scripts/setup_consequence_sources.sh);
the parser and cache are pure and unit-tested.
"""
import os
import sqlite3
import subprocess
from typing import Dict, List, Optional

# Sequence Ontology consequence terms, most-severe first (Ensembl VEP ranking).
_SEVERITY = [
    "transcript_ablation", "splice_acceptor_variant", "splice_donor_variant",
    "stop_gained", "frameshift_variant", "stop_lost", "start_lost",
    "transcript_amplification", "inframe_insertion", "inframe_deletion",
    "missense_variant", "protein_altering_variant", "splice_region_variant",
    "incomplete_terminal_codon_variant", "start_retained_variant",
    "stop_retained_variant", "synonymous_variant", "coding_sequence_variant",
    "mature_miRNA_variant", "5_prime_UTR_variant", "3_prime_UTR_variant",
    "non_coding_transcript_exon_variant", "intron_variant",
    "NMD_transcript_variant", "non_coding_transcript_variant",
    "upstream_gene_variant", "downstream_gene_variant",
    "TFBS_ablation", "regulatory_region_variant", "intergenic_variant",
]
_RANK = {c: i for i, c in enumerate(_SEVERITY)}


def most_severe_consequence(terms: List[str]) -> Optional[str]:
    terms = [t for t in terms if t]
    if not terms:
        return None
    return min(terms, key=lambda t: _RANK.get(t, 999))


def parse_vep_output(lines, mane_cache=None) -> Dict[str, str]:
    """Parse VEP tab output → rsid → consequence. Prefers the MANE transcript's
    consequence (via mane_cache.is_mane_transcript on the Feature column); falls
    back to the most-severe consequence across the variant's rows."""
    by_rsid: Dict[str, Dict[str, Optional[str]]] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 7:
            continue
        rsid, feature, cons_field = cols[0], cols[4], cols[6]
        row_cons = most_severe_consequence(cons_field.split(","))
        if not row_cons:
            continue
        entry = by_rsid.setdefault(rsid, {"mane": None, "best": None})
        if mane_cache is not None and mane_cache.is_mane_transcript(feature):
            entry["mane"] = most_severe_consequence(
                [c for c in (entry["mane"], row_cons) if c]
            )
        entry["best"] = most_severe_consequence(
            [c for c in (entry["best"], row_cons) if c]
        )
    return {rsid: (e["mane"] or e["best"]) for rsid, e in by_rsid.items() if (e["mane"] or e["best"])}


def build_vep_cache(vep_output_path: str, db_path: str, mane_cache=None) -> int:
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(vep_output_path) as fh:
        resolved = parse_vep_output(fh, mane_cache=mane_cache)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS vep_consequence")
        conn.execute("CREATE TABLE vep_consequence (rsid TEXT PRIMARY KEY, consequence TEXT)")
        conn.executemany(
            "INSERT OR REPLACE INTO vep_consequence VALUES (?, ?)", resolved.items()
        )
        conn.commit()
        return len(resolved)
    finally:
        conn.close()


def run_vep(marker_vcf: str, vep_cache_dir: str, output_path: str,
            assembly: str = "GRCh37") -> None:
    """Ops/refresh step: run VEP offline over the marker VCF. Not exercised in
    unit tests (requires VEP + the offline cache installed on the box)."""
    subprocess.run(
        ["vep", "--offline", "--cache", "--dir_cache", vep_cache_dir,
         "--assembly", assembly, "--tab", "--force_overwrite",
         "-i", marker_vcf, "-o", output_path],
        check=True,
    )


class VepConsequenceCache:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def consequence_for(self, rsid: Optional[str]) -> Optional[str]:
        if not rsid or not os.path.exists(self._db_path):
            return None
        try:
            conn = sqlite3.connect(self._db_path, timeout=1.0)
            try:
                row = conn.execute(
                    "SELECT consequence FROM vep_consequence WHERE rsid = ?", (rsid,)
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            return None
        return row[0] if row else None
