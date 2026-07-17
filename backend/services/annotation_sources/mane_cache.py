"""MANE Select canonical-transcript cache (U1).

Parses the NCBI MANE summary into a small SQLite lookup of gene → canonical
transcript (RefSeq + Ensembl). The consequence resolver uses it to pick the
canonical transcript's consequence when a variant has several transcript
consequences, so a real missense is not mislabelled by an intronic annotation
on an alternate transcript.
"""
import gzip
import os
import sqlite3
from typing import Dict, Optional

_MANE_SELECT = "MANE Select"


def _open(path: str):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def _versionless(transcript_id: str) -> str:
    return transcript_id.split(".")[0]


def build_mane_cache(summary_path: str, db_path: str) -> int:
    """Build the SQLite cache from the MANE summary. Returns the number of
    MANE Select genes stored."""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS mane")
        conn.execute("DROP TABLE IF EXISTS mane_transcripts")
        conn.execute(
            "CREATE TABLE mane (gene TEXT PRIMARY KEY, refseq_nuc TEXT, ensembl_nuc TEXT)"
        )
        conn.execute("CREATE TABLE mane_transcripts (transcript_id TEXT PRIMARY KEY)")

        count = 0
        with _open(summary_path) as fh:
            header = fh.readline().rstrip("\n").lstrip("#").split("\t")
            col = {name: i for i, name in enumerate(header)}
            for line in fh:
                cols = line.rstrip("\n").split("\t")
                if len(cols) <= col["MANE_status"]:
                    continue
                if cols[col["MANE_status"]] != _MANE_SELECT:
                    continue
                gene = cols[col["symbol"]]
                refseq = cols[col["RefSeq_nuc"]]
                ensembl = cols[col["Ensembl_nuc"]]
                conn.execute(
                    "INSERT OR REPLACE INTO mane VALUES (?, ?, ?)", (gene, refseq, ensembl)
                )
                for tid in (refseq, ensembl):
                    if tid:
                        conn.execute(
                            "INSERT OR IGNORE INTO mane_transcripts VALUES (?)", (tid,)
                        )
                        conn.execute(
                            "INSERT OR IGNORE INTO mane_transcripts VALUES (?)",
                            (_versionless(tid),),
                        )
                count += 1
        conn.commit()
        return count
    finally:
        conn.close()


class ManeCache:
    """Read-only lookup over the MANE cache."""

    def __init__(self, db_path: str):
        self._db_path = db_path

    def canonical_transcript(self, gene: Optional[str]) -> Optional[Dict[str, str]]:
        if not gene:
            return None
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT refseq_nuc, ensembl_nuc FROM mane WHERE gene = ?", (gene,)
            ).fetchone()
        finally:
            conn.close()
        return {"refseq": row[0], "ensembl": row[1]} if row else None

    def is_mane_transcript(self, transcript_id: Optional[str]) -> bool:
        if not transcript_id:
            return False
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM mane_transcripts WHERE transcript_id = ? OR transcript_id = ?",
                (transcript_id, _versionless(transcript_id)),
            ).fetchone()
        finally:
            conn.close()
        return row is not None
