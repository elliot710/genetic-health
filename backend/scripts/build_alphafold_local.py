#!/usr/bin/env python3
"""
AlphaFold Human Proteome — Local ETL
=====================================
Downloads UP000005640_9606_HUMAN_v6.tar from EBI FTP, streams through it
entry-by-entry, parses per-residue pLDDT from mmCIF files, and writes a
compact SQLite index to data_sources/alphafold/human_v6.db.

The resulting SQLite is <20 MB and replaces expensive BigQuery lookups.

Usage:
    python -m backend.scripts.build_alphafold_local [--force] [--out PATH]

Options:
    --force     Rebuild even if DB already exists
    --out PATH  Override output path (default: data_sources/alphafold/human_v6.db)
    --tar URL   Override download URL
    --skip-dl   Use an already-downloaded tar at /tmp/alphafold_human_v6.tar

License / Attribution:
    AlphaFold data is available under CC-BY-4.0.
    Cite: Fleming J. et al., JMB (2025); Jumper J. et al., Nature (2021).
"""
from __future__ import annotations

import argparse
import gzip
import io
import logging
import re
import sqlite3
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("af_etl")

TAR_URL = (
    "https://ftp.ebi.ac.uk/pub/databases/alphafold/latest/"
    "UP000005640_9606_HUMAN_v6.tar"
)
UNIPROT_GENE_URL = (
    "https://rest.uniprot.org/uniprotkb/stream"
    "?query=organism_id:9606"
    "&format=tsv"
    "&fields=accession,gene_names,protein_name"
    "&size=500"
)
DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    uniprot_id       TEXT PRIMARY KEY,
    entry_id         TEXT NOT NULL,
    gene_symbols     TEXT,          -- comma-separated gene names
    protein_name     TEXT,
    global_confidence REAL,         -- mean pLDDT (0–100)
    plddt_very_high  REAL,          -- fraction of residues with pLDDT > 90
    plddt_confident  REAL,          -- fraction 70–90
    plddt_low        REAL,          -- fraction 50–70
    plddt_very_low   REAL,          -- fraction < 50
    residue_count    INTEGER,
    model_version    TEXT,
    fragment         INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_pred_entry ON predictions(entry_id);

CREATE TABLE IF NOT EXISTS gene_map (
    gene_symbol  TEXT PRIMARY KEY,
    uniprot_id   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# ─── mmCIF pLDDT parser ──────────────────────────────────────────────────────

def _parse_cif_plddt(cif_bytes: bytes) -> Tuple[List[float], str, str, str]:
    """Parse an AlphaFold mmCIF.gz bytes.

    Returns:
        (plddt_values, protein_name, entry_id, model_version)
        plddt_values is one value per residue (CA atom only).
    """
    try:
        text = gzip.decompress(cif_bytes).decode("utf-8", errors="ignore")
    except Exception:
        return [], "", "", ""

    plddt: List[float] = []
    protein_name = ""
    entry_id = ""
    model_version = ""

    # Fast metadata extraction via regex
    m = re.search(r"_entry\.id\s+(\S+)", text)
    if m:
        entry_id = m.group(1).strip("'\"")

    m = re.search(r"_struct\.title\s+'([^']+)'", text)
    if not m:
        m = re.search(r'_struct\.title\s+"([^"]+)"', text)
    if not m:
        m = re.search(r"_struct\.title\s+(\S.+)", text)
    if m:
        protein_name = m.group(1).strip("'\" ")

    m = re.search(r"AF-[A-Z0-9]+-F\d+-(model_v\d+)", entry_id)
    if not m and entry_id:
        m = re.search(r"model_v(\d+)", text[:500])
    if m:
        model_version = m.group(1) if "model_v" in m.group(0) else f"v{m.group(1)}"

    # ── atom_site loop: find B_iso_or_equiv column index ─────────────────────
    # mmCIF loops look like:
    #   loop_
    #   _atom_site.col1
    #   _atom_site.col2   ← find B_iso_or_equiv and label_atom_id here
    #   ATOM 1 CA ...     ← data rows start here
    # We only collect CA atoms (one per residue) for efficiency.

    # Locate the atom_site loop
    loop_start = text.find("loop_\n_atom_site.")
    if loop_start == -1:
        loop_start = text.find("loop_\r\n_atom_site.")
    if loop_start == -1:
        return plddt, protein_name, entry_id, model_version

    # Read column headers
    columns: List[str] = []
    b_col = -1
    atom_id_col = -1
    group_col = -1

    pos = loop_start + len("loop_\n")
    lines = text[pos:].split("\n")
    data_start_line = 0
    for i, ln in enumerate(lines):
        ln_s = ln.strip()
        if ln_s.startswith("_atom_site."):
            col_name = ln_s.split(".")[1] if "." in ln_s else ln_s
            idx = len(columns)
            if "B_iso_or_equiv" in col_name:
                b_col = idx
            elif col_name in ("label_atom_id", "auth_atom_id") and atom_id_col == -1:
                atom_id_col = idx
            elif col_name == "group_PDB":
                group_col = idx
            columns.append(col_name)
        elif columns:
            # First non-header line after headers = data starts here
            data_start_line = i
            break

    if b_col == -1:
        return plddt, protein_name, entry_id, model_version

    # Parse data rows — only CA atoms to get one pLDDT per residue
    for ln in lines[data_start_line:]:
        ln_s = ln.strip()
        if not ln_s or ln_s.startswith("_") or ln_s == "loop_" or ln_s.startswith("#"):
            # End of atom_site loop
            if plddt:  # stop after first atom_site block that had data
                break
            continue

        # Quick filter: skip non-ATOM lines if possible
        if group_col == 0 and not (ln_s.startswith("ATOM") or ln_s.startswith("HETATM")):
            continue

        parts = ln_s.split()
        if len(parts) <= b_col:
            continue

        # Filter to CA atoms only
        if atom_id_col >= 0 and atom_id_col < len(parts):
            if parts[atom_id_col] != "CA":
                continue
        elif atom_id_col == -1:
            # No atom_id column — take every 4th entry as heuristic for CA
            # (not ideal; fall back to all atoms / 4 as rough residue count)
            pass

        try:
            val = float(parts[b_col])
            plddt.append(val)
        except ValueError:
            continue

    return plddt, protein_name, entry_id, model_version


def _compute_stats(plddt: List[float]) -> Tuple[float, float, float, float, float]:
    """Return (mean, frac_very_high, frac_confident, frac_low, frac_very_low)."""
    if not plddt:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    n = len(plddt)
    mean = sum(plddt) / n
    vh  = sum(1 for v in plddt if v > 90) / n
    conf = sum(1 for v in plddt if 70 < v <= 90) / n
    low  = sum(1 for v in plddt if 50 < v <= 70) / n
    vlow = sum(1 for v in plddt if v <= 50) / n
    return mean, vh, conf, low, vlow


# ─── UniProt gene mapping ────────────────────────────────────────────────────

def _download_uniprot_gene_map() -> Dict[str, Tuple[str, List[str]]]:
    """Download reviewed+unreviewed human UniProt accession→gene+name mapping.

    Returns: {uniprot_id: (protein_name, [gene_symbols, ...])}
    """
    log.info("Downloading UniProt human gene mapping …")
    # Reviewed SwissProt first
    mappings: Dict[str, Tuple[str, List[str]]] = {}

    for reviewed in ("true", "false"):
        url = (
            "https://rest.uniprot.org/uniprotkb/stream"
            f"?query=organism_id:9606+AND+reviewed:{reviewed}"
            "&format=tsv"
            "&fields=accession,gene_names,protein_name"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "dna-toolkit/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            log.warning(f"UniProt download failed (reviewed={reviewed}): {e}")
            continue

        for line in raw.splitlines()[1:]:  # skip header
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            acc = parts[0].strip()
            genes_raw = parts[1].strip() if len(parts) > 1 else ""
            prot_name = parts[2].strip() if len(parts) > 2 else ""
            # gene_names field: "GENE1 GENE2 ..." space-separated, primary first
            genes = [g.strip() for g in genes_raw.split() if g.strip()]
            if acc and acc not in mappings:
                mappings[acc] = (prot_name, genes)

        log.info(f"  reviewed={reviewed}: {len(mappings)} total entries so far")

    log.info(f"UniProt mapping: {len(mappings)} proteins loaded")
    return mappings


# ─── SQLite helpers ───────────────────────────────────────────────────────────

def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-32000")  # 32 MB
    conn.executescript(DB_SCHEMA)
    conn.commit()
    return conn


def _bulk_insert(conn: sqlite3.Connection, rows: List[tuple]) -> None:
    conn.executemany(
        """
        INSERT OR REPLACE INTO predictions
            (uniprot_id, entry_id, gene_symbols, protein_name,
             global_confidence, plddt_very_high, plddt_confident,
             plddt_low, plddt_very_low, residue_count, model_version, fragment)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    conn.commit()


def _build_gene_map(conn: sqlite3.Connection) -> None:
    """Populate gene_map from predictions table."""
    conn.execute("DELETE FROM gene_map")
    cur = conn.execute("SELECT uniprot_id, gene_symbols FROM predictions WHERE gene_symbols IS NOT NULL")
    gene_rows: List[tuple] = []
    seen: set = set()
    for uniprot_id, gene_str in cur.fetchall():
        for g in gene_str.split(","):
            g = g.strip().upper()
            if g and g not in seen:
                gene_rows.append((g, uniprot_id))
                seen.add(g)
    conn.executemany(
        "INSERT OR IGNORE INTO gene_map (gene_symbol, uniprot_id) VALUES (?,?)",
        gene_rows,
    )
    conn.commit()
    log.info(f"gene_map: {len(gene_rows)} entries")


# ─── Main ETL ────────────────────────────────────────────────────────────────

def run_etl(
    tar_url: str = TAR_URL,
    out_path: Optional[Path] = None,
    force: bool = False,
    skip_dl: bool = False,
    local_tar: Optional[str] = None,
) -> Path:
    # Resolve output path
    if out_path is None:
        script_dir = Path(__file__).resolve().parent
        repo_root = script_dir.parent.parent
        out_path = repo_root / "data_sources" / "alphafold" / "human_v6.db"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and not force:
        log.info(f"DB already exists at {out_path} — use --force to rebuild")
        return out_path

    # ── Step 1: UniProt gene mapping ─────────────────────────────────────────
    uniprot_map = _download_uniprot_gene_map()  # {acc: (prot_name, [genes])}

    # ── Step 2: Open DB ───────────────────────────────────────────────────────
    log.info(f"Creating SQLite at {out_path}")
    conn = _open_db(out_path)

    # ── Step 3: Stream tar ────────────────────────────────────────────────────
    log.info(f"Streaming AlphaFold tar: {tar_url}")

    if local_tar:
        fobj: io.RawIOBase = open(local_tar, "rb")  # type: ignore[assignment]
        tar_src = local_tar
    else:
        req = urllib.request.Request(tar_url, headers={"User-Agent": "dna-toolkit/1.0"})
        fobj = urllib.request.urlopen(req, timeout=600)  # type: ignore[assignment]
        tar_src = tar_url

    t0 = time.time()
    processed = 0
    skipped = 0
    batch: List[tuple] = []
    BATCH_SIZE = 500

    try:
        with tarfile.open(fileobj=fobj, mode="r|") as tf:
            for member in tf:
                if not member.isfile():
                    continue

                name = member.name
                # Skip PAE files — they're large and not needed
                if "predicted_aligned_error" in name:
                    tf.members = []  # clear queue
                    continue
                if not name.endswith(".cif.gz"):
                    continue

                # Extract UniProt accession from filename: AF-{acc}-F{n}-model_v6.cif.gz
                m = re.search(r"AF-([A-Z0-9]+)-F(\d+)-model_v(\d+)\.cif\.gz$", name)
                if not m:
                    skipped += 1
                    continue

                uniprot_id = m.group(1)
                fragment = int(m.group(2))

                fdata = tf.extractfile(member)
                if fdata is None:
                    continue
                cif_bytes = fdata.read()

                plddt, cif_prot_name, entry_id, model_ver = _parse_cif_plddt(cif_bytes)
                if not plddt:
                    skipped += 1
                    continue

                mean, vh, conf, low, vlow = _compute_stats(plddt)

                # Gene symbols + protein name from UniProt mapping
                prot_name, genes = uniprot_map.get(uniprot_id, (cif_prot_name, []))
                if not prot_name:
                    prot_name = cif_prot_name
                gene_str = ",".join(genes) if genes else None

                if not entry_id:
                    entry_id = f"AF-{uniprot_id}-F{fragment}-model_v{m.group(3)}"
                if not model_ver:
                    model_ver = f"v{m.group(3)}"

                batch.append((
                    uniprot_id, entry_id, gene_str, prot_name or None,
                    round(mean, 4), round(vh, 6), round(conf, 6),
                    round(low, 6), round(vlow, 6),
                    len(plddt), model_ver, fragment,
                ))
                processed += 1

                if len(batch) >= BATCH_SIZE:
                    _bulk_insert(conn, batch)
                    batch = []

                if processed % 1000 == 0:
                    elapsed = time.time() - t0
                    log.info(
                        f"  {processed} proteins processed, {skipped} skipped "
                        f"({elapsed:.0f}s, {processed/elapsed:.0f}/s)"
                    )

    finally:
        fobj.close()

    if batch:
        _bulk_insert(conn, batch)

    elapsed = time.time() - t0
    log.info(f"Tar processing done: {processed} proteins in {elapsed:.1f}s")

    # ── Step 4: Build gene index ──────────────────────────────────────────────
    log.info("Building gene_map index …")
    _build_gene_map(conn)

    # ── Step 5: Write metadata ────────────────────────────────────────────────
    import datetime
    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('build_date', ?)",
                 (datetime.datetime.utcnow().isoformat(),))
    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('source', ?)", (tar_src,))
    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('version', 'v6')")
    cur = conn.execute("SELECT COUNT(*) FROM predictions")
    count = cur.fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('protein_count', ?)", (str(count),))
    conn.commit()

    # Compact
    conn.execute("VACUUM")
    conn.close()

    size_mb = out_path.stat().st_size / 1e6
    log.info(f"Done. {count} proteins → {out_path} ({size_mb:.1f} MB)")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build local AlphaFold SQLite index")
    parser.add_argument("--force", action="store_true", help="Rebuild even if DB exists")
    parser.add_argument("--out", type=Path, help="Output SQLite path")
    parser.add_argument("--tar", default=TAR_URL, help="Tar URL or local path")
    parser.add_argument("--skip-dl", dest="skip_dl", action="store_true")
    parser.add_argument("--local-tar", dest="local_tar", help="Use local tar file")
    args = parser.parse_args()

    run_etl(
        tar_url=args.tar,
        out_path=args.out,
        force=args.force,
        skip_dl=args.skip_dl,
        local_tar=args.local_tar,
    )
