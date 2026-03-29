"""
AlphaFold Local Service
=======================
Serves protein structure confidence data from the locally-built SQLite index
(data_sources/alphafold/human_v6.db) built by scripts/build_alphafold_local.py.

Replaces the BigQuery `deepmind_alphafold.metadata` lookups, returning
the identical dict schema so nothing downstream needs to change.

Lookup priority:
    1. gene_symbol → gene_map → uniprot_id → predictions  (primary)
    2. uniprot_id direct                                   (fallback)

Thread/async safety: sqlite3 is opened once per process with WAL mode;
read-only SELECT queries are safe from multiple async tasks via asyncio.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data_sources" / "alphafold" / "human_v6.db"


class AlphaFoldLocalService:
    """Read-only access to the local AlphaFold SQLite index."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = Path(db_path or os.environ.get("ALPHAFOLD_LOCAL_DB", str(_DEFAULT_DB_PATH)))
        self._conn: Optional[sqlite3.Connection] = None
        self._available = False
        self._protein_count = 0

    @property
    def available(self) -> bool:
        return self._available

    @property
    def protein_count(self) -> int:
        return self._protein_count

    def _connect(self) -> Optional[sqlite3.Connection]:
        if not self._db_path.exists():
            return None
        conn = sqlite3.connect(
            f"file:{self._db_path}?mode=ro",  # read-only
            uri=True,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA cache_size=-16000")  # 16 MB per connection
        return conn

    def ensure_loaded(self) -> bool:
        """Open the SQLite and verify it's ready. Returns True if available."""
        if self._available:
            return True
        try:
            conn = self._connect()
            if conn is None:
                logger.debug(f"AlphaFold local DB not found at {self._db_path}")
                return False
            cur = conn.execute("SELECT value FROM metadata WHERE key='protein_count'")
            row = cur.fetchone()
            if row:
                self._protein_count = int(row[0])
            self._conn = conn
            self._available = True
            logger.info(
                f"AlphaFold local: loaded {self._protein_count:,} proteins from {self._db_path}"
            )
            return True
        except Exception as e:
            logger.warning(f"AlphaFold local: failed to open DB: {e}")
            return False

    # ─── Public lookup methods ────────────────────────────────────────────────

    def lookup_gene(self, gene_symbol: str) -> Dict[str, Any]:
        """Look up AlphaFold data for a given gene symbol.

        Returns the same dict schema as the BigQuery implementation:
        {
            "gene": str, "found": bool, "source": "alphafold_local",
            "entry_id": str, "uniprot_id": str, "protein_name": list[str],
            "global_confidence": float (0-100), "plddt_very_high": float (0-1),
            "plddt_confident": float (0-1), "plddt_low": float (0-1),
            "plddt_very_low": float (0-1), "model_date": str,
            "all_isoforms": list[{entry_id, uniprot_id, confidence}]
        }
        """
        if not self._available:
            return {"gene": gene_symbol, "found": False}

        try:
            conn = self._conn
            # Gene → uniprot_id
            cur = conn.execute(
                "SELECT uniprot_id FROM gene_map WHERE gene_symbol = ?",
                (gene_symbol.upper(),),
            )
            row = cur.fetchone()
            if row is None:
                return {"gene": gene_symbol, "found": False, "source": "alphafold_local"}

            return self._lookup_by_uniprot(row["uniprot_id"], gene_symbol)
        except Exception as e:
            logger.warning(f"AlphaFold lookup_gene({gene_symbol}): {e}")
            return {"gene": gene_symbol, "found": False}

    def lookup_uniprot(self, uniprot_id: str) -> Dict[str, Any]:
        """Look up by UniProt accession directly."""
        if not self._available:
            return {"uniprot_id": uniprot_id, "found": False}
        try:
            return self._lookup_by_uniprot(uniprot_id)
        except Exception as e:
            logger.warning(f"AlphaFold lookup_uniprot({uniprot_id}): {e}")
            return {"uniprot_id": uniprot_id, "found": False}

    def bulk_lookup_genes(self, gene_symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch lookup of multiple gene symbols. Returns {gene: result_dict}."""
        if not self._available or not gene_symbols:
            return {g: {"gene": g, "found": False} for g in gene_symbols}

        results: Dict[str, Dict[str, Any]] = {}
        upper_to_orig = {g.upper(): g for g in gene_symbols}

        try:
            conn = self._conn
            placeholders = ",".join("?" * len(gene_symbols))
            upper_symbols = list(upper_to_orig.keys())

            # Gene → uniprot mapping
            cur = conn.execute(
                f"SELECT gene_symbol, uniprot_id FROM gene_map WHERE gene_symbol IN ({placeholders})",
                upper_symbols,
            )
            gene_to_uniprot = {row["gene_symbol"]: row["uniprot_id"] for row in cur.fetchall()}

            # Bulk fetch predictions
            uniprot_ids = list(set(gene_to_uniprot.values()))
            pred_map: Dict[str, sqlite3.Row] = {}
            if uniprot_ids:
                ph2 = ",".join("?" * len(uniprot_ids))
                cur2 = conn.execute(
                    f"SELECT * FROM predictions WHERE uniprot_id IN ({ph2})",
                    uniprot_ids,
                )
                for row in cur2.fetchall():
                    pred_map[row["uniprot_id"]] = row

            for upper_gene, orig_gene in upper_to_orig.items():
                uniprot_id = gene_to_uniprot.get(upper_gene)
                if not uniprot_id or uniprot_id not in pred_map:
                    results[orig_gene] = {"gene": orig_gene, "found": False, "source": "alphafold_local"}
                    continue
                p = pred_map[uniprot_id]
                results[orig_gene] = self._row_to_dict(p, orig_gene)

        except Exception as e:
            logger.warning(f"AlphaFold bulk_lookup_genes: {e}")
            for g in gene_symbols:
                if g not in results:
                    results[g] = {"gene": g, "found": False}

        return results

    # ─── Internal helpers ─────────────────────────────────────────────────────

    def _lookup_by_uniprot(
        self, uniprot_id: str, gene_symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        conn = self._conn
        # Fetch all fragments (isoforms) for this accession
        cur = conn.execute(
            "SELECT * FROM predictions WHERE uniprot_id = ? ORDER BY fragment",
            (uniprot_id,),
        )
        rows = cur.fetchall()
        if not rows:
            return {
                "gene": gene_symbol or uniprot_id,
                "found": False,
                "source": "alphafold_local",
            }

        # Primary: fragment 1 (or highest confidence fragment)
        primary = max(rows, key=lambda r: r["global_confidence"] or 0)
        if gene_symbol is None:
            gene_symbols = (primary["gene_symbols"] or "").split(",")
            gene_symbol = gene_symbols[0].strip() if gene_symbols else uniprot_id

        return self._row_to_dict(primary, gene_symbol, all_rows=rows)

    def _row_to_dict(
        self, row: sqlite3.Row, gene_symbol: str, all_rows: Optional[List[sqlite3.Row]] = None
    ) -> Dict[str, Any]:
        # Protein name: stored as primary name string (may contain semicolons for aliases)
        raw_prot = row["protein_name"] or ""
        protein_names = [n.strip() for n in raw_prot.split(";") if n.strip()] if raw_prot else []

        return {
            "gene": gene_symbol,
            "found": True,
            "source": "alphafold_local",
            "entry_id": row["entry_id"],
            "uniprot_id": row["uniprot_id"],
            "protein_name": protein_names,
            "global_confidence": row["global_confidence"],
            "plddt_very_high": row["plddt_very_high"],
            "plddt_confident": row["plddt_confident"],
            "plddt_low": row["plddt_low"],
            "plddt_very_low": row["plddt_very_low"],
            "model_date": "",  # not in CIF; set to empty (consistent with v4/v6)
            "all_isoforms": [
                {
                    "entry_id": r["entry_id"],
                    "uniprot_id": r["uniprot_id"],
                    "confidence": r["global_confidence"],
                }
                for r in (all_rows or [row])
            ],
        }


# ─── Singleton ────────────────────────────────────────────────────────────────

_instance: Optional[AlphaFoldLocalService] = None


def get_alphafold_local_service() -> AlphaFoldLocalService:
    global _instance
    if _instance is None:
        _instance = AlphaFoldLocalService()
        _instance.ensure_loaded()
    return _instance
