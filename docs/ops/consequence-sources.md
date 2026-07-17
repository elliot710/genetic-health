# Offline consequence sources — ops

Four offline, commercial-safe sources give molecular-consequence coverage for the
consumer-array marker set (GRCh37), feeding the consequence resolver
(`backend/services/annotation_sources/consequence_resolver.py`) and, through it,
the reliability predicate + health gates.

## Sources (GRCh37)

| Source | Size | License | Cache |
|---|---|---|---|
| MANE Select | ~1 MB | free | `.mane_cache/mane.db` |
| dbSNP b151 GRCh37 VCF | ~16 GB | public domain | `.dbsnp_cache/dbsnp_mc.db` |
| Ensembl VEP offline cache (r113 GRCh37) + tool | ~18 GB | open | `.vep_cache/vep_consequence.db` |
| SnpEff + GRCh37.75 db | ~1 GB | LGPL | `.snpeff_cache/snpeff_consequence.db` |

Non-commercial sources (dbNSFP, CADD whole-genome) are deliberately excluded.

## Assembly

The consumer-array marker set is **GRCh37** (`genetic_markers` positions). All
position-based sources are GRCh37. MANE is GRCh38-only but is used only as a
gene→canonical-transcript map (assembly-agnostic). dbSNP MC is rsid-keyed.

## Disk / image

- ~35 GB on the worker box's `data_sources/` volume (dbSNP + VEP cache dominate).
- VEP needs Perl; SnpEff needs Java. Keep these in the ETL/refresh image, not the
  per-analysis hot path — VEP/SnpEff run once over the marker set, never per
  analysis (`consequence_resolver` only reads the SQLite caches at analysis time).

## Runbook

1. `bash backend/scripts/setup_consequence_sources.sh --check` — verify URLs.
2. `bash backend/scripts/setup_consequence_sources.sh` — download all four,
   install SnpEff, build the MANE + dbSNP caches.
3. `uv run python -m backend.scripts.refresh_consequence_caches` — export the
   marker set, run VEP + SnpEff over it, build the VEP + SnpEff caches. Re-run
   this whenever the marker set grows.
4. `uv run python -m backend.scripts.report_consequence_coverage` — confirm the
   coverage jump.

Caches are rebuilt from `data_sources/` and are gitignored.
