"""dbSNP molecular-consequence cache (U2).

Streams the dbSNP GRCh37 (b151) VCF and maps its function-class boolean INFO
flags to Sequence Ontology consequence terms, keyed by rsid. Consumer arrays
report rsids, so this is the direct rsid → consequence fill.
"""
import gzip
import os
import sqlite3
from typing import List, Optional

# b151 GRCh37 function-class flags → SO consequence terms. Ordered by severity so
# the stored list leads with the most damaging consequence.
_FLAG_TO_SO = [
    ("NSN", "stop_gained"),          # nonsense
    ("NSF", "frameshift_variant"),
    ("ASS", "splice_acceptor_variant"),
    ("DSS", "splice_donor_variant"),
    ("NSM", "missense_variant"),
    ("SYN", "synonymous_variant"),
    ("U3", "3_prime_UTR_variant"),
    ("U5", "5_prime_UTR_variant"),
    ("INT", "intron_variant"),
    ("R3", "downstream_gene_variant"),
    ("R5", "upstream_gene_variant"),
]


def _open(path: str):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def _consequences_from_info(info: str) -> List[str]:
    flags = {tok for tok in info.split(";") if "=" not in tok}
    return [so for flag, so in _FLAG_TO_SO if flag in flags]


def build_dbsnp_mc_cache(vcf_path: str, db_path: str, limit: Optional[int] = None) -> int:
    """Build the SQLite rsid→consequence cache. `limit` caps records processed
    (for partial/verification builds). Returns rows stored (records with at least
    one function-class flag)."""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS dbsnp_mc")
        conn.execute("CREATE TABLE dbsnp_mc (rsid TEXT PRIMARY KEY, consequences TEXT)")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA journal_mode=MEMORY")

        stored = 0
        seen = 0
        batch = []
        with _open(vcf_path) as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                seen += 1
                if limit is not None and seen > limit:
                    break
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 8:
                    continue
                rsid = cols[2]
                if not rsid.startswith("rs"):
                    continue
                terms = _consequences_from_info(cols[7])
                if not terms:
                    continue
                batch.append((rsid, ",".join(terms)))
                stored += 1
                if len(batch) >= 5000:
                    conn.executemany("INSERT OR REPLACE INTO dbsnp_mc VALUES (?, ?)", batch)
                    batch.clear()
        if batch:
            conn.executemany("INSERT OR REPLACE INTO dbsnp_mc VALUES (?, ?)", batch)
        conn.commit()
        return stored
    finally:
        conn.close()


class DbsnpMcCache:
    """Read-only rsid → consequence lookup."""

    def __init__(self, db_path: str):
        self._db_path = db_path

    def consequence_for_rsid(self, rsid: Optional[str]) -> List[str]:
        if not rsid:
            return []
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT consequences FROM dbsnp_mc WHERE rsid = ?", (rsid,)
            ).fetchone()
        finally:
            conn.close()
        return row[0].split(",") if row and row[0] else []
