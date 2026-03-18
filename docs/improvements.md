# Genetic Health Analysis Toolkit — Known Issues & Improvements

> **Scope:** All backend and frontend modules as of March 2026  
> **Issues found:** 20 bugs, 3 data quality problems, 5 architectural gaps  
> Status ratings: 🔴 CRITICAL | 🟠 HIGH | 🟡 MEDIUM | 🟢 LOW  

---

## Table of Contents

1. [Data Source Issues](#1-data-source-issues)
2. [Insight Generator Bugs](#2-insight-generator-bugs)
3. [Scoring Engine Issues](#3-scoring-engine-issues)
4. [Analysis Pipeline Bugs](#4-analysis-pipeline-bugs)
5. [Data Quality Issues](#5-data-quality-issues)
6. [Architectural Gaps](#6-architectural-gaps)
7. [Frontend Issues](#7-frontend-issues)
8. [Fix Priority Order](#8-fix-priority-order)

---

## 1. Data Source Issues

---

### BUG-01 — gnomAD data virtually absent 🔴 CRITICAL

**File:** `services/gnomad_local.py`, ETL pipeline  
**Tables affected:** `gnomad_variants`, `shared_variant_annotations.gnomad_data`

**Problem:**  
Only **305 of 714,586** shared annotations have gnomAD data populated (0.04%). This renders 40% of the scoring engine's weight unavailable:

| Dead source | Weight lost |
|-------------|-------------|
| CADD PHRED | 0.15 |
| gnomAD AF | 0.10 |
| SIFT | 0.05 |
| PolyPhen | 0.05 |
| PhyloP conservation | 0.05 |
| SpliceAI | 0.05 |
| **Total** | **0.45** |

All variant pathogenicity scores are computed on at most 55% of their intended evidence base.

**Impact:**  
- `uncommon_mutations` generator always produces 0 results (requires gnomAD AF in range 0.001–0.05)
- Common benign variants with no ClinVar data cannot be downgraded via high population frequency
- CADD/SIFT/PolyPhen scores (excellent computational predictors) are unused

**Fix:**  
1. Verify `gnomad_variants` table is populated: `SELECT COUNT(*) FROM gnomad_variants;`
2. Re-run gnomAD ETL import script against the local gnomAD TSV files in `data_sources/gnomad/`
3. Re-run `annotation_source_configs` to enable the gnomAD local source
4. After ETL: run `SELECT COUNT(*) FROM shared_variant_annotations WHERE gnomad_data->>'found' = 'true';` to confirm

---

### BUG-02 — AlphaMissense hit rate near zero 🟠 HIGH

**File:** `services/alpha_missense_local.py` (tabix lookup)  
**Table:** `shared_variant_annotations.alpha_missense_data`

**Problem:**  
Only 2,504 of 714,586 annotations have AlphaMissense data (`found:true`) = **0.35%**. AlphaMissense covers ~70M human missense variants and should match substantially more user variants.

**Observed in job logs:**
```
AlphaMissense: 181 found (0.17%) of 105,204 RSIDs queried in last run
```

**Likely root causes (in order of probability):**
1. **Chromosome naming mismatch**: tabix files use `chr1` but queries use `1` or vice versa
2. **Position off-by-1**: 0-based vs 1-based coordinate mismatch between tabix and the position stored in `genetic_markers`
3. **Wrong build**: Tabix indexed on GRCh38 but user variants are GRCh37
4. **Incomplete tabix coverage**: data_sources/alpha_missense/ may contain only one chromosome file

**Fix:**
```bash
# Check the tabix header to see chromosome notation
docker exec dna_toolkit-backend-1 uv run python -c "
import pysam
tb = pysam.TabixFile('data_sources/alpha_missense/AlphaMissense_hg38.tsv.gz')
print(tb.contigs[:5])
"
# Compare to genetic_markers.chromosome values
docker exec -it dna_toolkit-postgres-1 psql -U postgres genetic_health_db \
  -c "SELECT chromosome, COUNT(*) FROM genetic_markers GROUP BY chromosome ORDER BY 2 DESC LIMIT 10;"
```

---

### BUG-03 — Ensembl VEP data lacks gene_symbol for 99.8% of records 🟠 HIGH

**File:** `services/shared_annotation_service.py`, `services/insight_generators/base.py`  
**Function:** `extract_gene_and_consequence()`

**Problem:**  
714,586 annotations have `ensembl_data` populated. But only 1,532 have `gene_symbol` in `transcript_consequences`. The `extract_gene_and_consequence()` function falls back correctly to `rsid_gene_map` for gene resolution, but gene-based variant matching in all insight generators depends on this gene assignment being correct and complete.

**Why it matters:**
- `rsid_gene_map` has 60.5% coverage (built from ClinVar DB + Ensembl position lookup in Phase 1)
- The remaining 39.5% of variants cannot be gene-matched to the registry
- Gene-type mappings in `variant_mappings` (e.g. CYP2D6 drug metabolizer entries) can only be hit if the gene was resolved

**Fix:**  
Investigate why Ensembl VEP responses don't include transcript_consequences:
1. Check if VEP API is returning `intergenic_consequences` instead of `transcript_consequences` (happens for intergenic variants)
2. Check VEP response cache — if many responses are cached from a version that didn't include `gene_symbol`
3. Run alembic revision 009 cleared broken annotations — verify those were re-annotated after clearing

---

## 2. Insight Generator Bugs

---

### BUG-04 — panel_marker_configs completely disconnected from insight generation 🔴 CRITICAL

**File:** ALL insight generators in `services/insight_generators/`  
**Table:** `panel_marker_configs`

**Problem:**  
`panel_marker_configs` contains 20,221 carefully curated markers across 14 panels, including:
- BRCA1 (rs80357906), BRCA2 (rs80358981), TP53 (rs28934578) in `rare_mutations`
- APOE-ε4 in `health`
- CYP2D6/CYP2C19/VKORC1 in `drug_responses`

**None of these ever feed into insight generation.** No generator reads `panel_marker_configs`. The table is only used by `DiscoveryService._infer_panels()` to avoid re-discovering known markers.

The actual insight generators read exclusively from `variant_mappings`. Many panel_marker_configs entries have NO corresponding `variant_mappings` entry — meaning high-value curated markers like BRCA1 pathogenic variants are silently ignored.

**Evidence:**  
```sql
-- Curated panel entries with no variant_mapping match:
SELECT p.rsid, p.panel_id, p.gene FROM panel_marker_configs p
LEFT JOIN variant_mappings v ON v.key = p.rsid AND v.map_type = 'rsid'
WHERE v.id IS NULL AND p.is_active = TRUE;
-- Returns thousands of rows including BRCA1/2 rsids
```

**Fix:**  
Two options:
1. **Preferred**: Write a one-time migration script to sync `panel_marker_configs` → `variant_mappings` for any rsid not already present. Use category-appropriate templates.
2. **Alternative**: Add `panel_marker_configs` as a lookup step within `rare_mutations` generator and `health` generator (high-importance panels only).

---

### BUG-05 — uncommon_mutations generator always produces 0 results 🔴 CRITICAL

**File:** `services/insight_generators/uncommon_mutations.py`  
**Function:** `generate_uncommon_mutations()`

**Problem:**  
The generator requires `0.001 ≤ population_frequency ≤ 0.05` — the "uncommon" range. `extract_frequency()` tries these sources in order:
1. Ensembl colocated_variants gnomAD frequencies
2. gnomAD local AF
3. 1000G global AF

With gnomAD data at 0.04% coverage (BUG-01), virtually no variants have their frequency populated. Result: `freq = 0.0` for 99.96%+ of variants → condition `freq >= 0.001` never satisfied → **0 insights always**.

**Fix:**  
- Fix BUG-01 (gnomAD ETL) as the primary fix
- Short-term: expand `extract_frequency()` to include 1000G global AF as a frequency source, since `thousand_genomes_data` is present for 100% of annotations (though populated ratio unknown)
- Verify 1000G data has `global_af` or equivalent: `SELECT thousand_genomes_data->'global_af' FROM shared_variant_annotations WHERE thousand_genomes_data IS NOT NULL LIMIT 5;`

---

### BUG-06 — zygosity_adjust alias table incomplete 🟠 HIGH

**File:** `services/insight_generators/base.py`  
**Function:** `zygosity_adjust()`, `_LEVEL_ALIASES`

**Problem:**  
`_LEVEL_ALIASES` maps non-standard risk levels to the 5-level severity ladder. However, several values used in manually-seeded variant mappings are NOT in the alias table:

| Value | Appears in | Effect |
|-------|-----------|--------|
| `mildly_reduced` | methylation mappings | No zygosity adjustment — always shows baseline |
| `b12_dependent` | methylation mappings | Same |
| `slow_processing` | methylation/wellness | Same |
| `variant_detected` | personality/wellness | Same |
| `sensitive` | nutrition mappings | Same |

When `idx = None`, `zygosity_adjust` returns the `level` argument unchanged. Homozygous alternate users get the same insight severity as heterozygous users.

**Fix:**
```python
# In base.py, add to _LEVEL_ALIASES:
_LEVEL_ALIASES = {
    ...existing entries...,
    'mildly_reduced': 'average',   # methylation
    'b12_dependent': 'moderate',   # methylation
    'slow_processing': 'moderate', # methylation/wellness
    'variant_detected': 'moderate', # personality
    'sensitive': 'moderate',        # nutrition
}
```

Also add a warning log for any unrecognized level in `zygosity_adjust` to catch future issues.

---

### BUG-07 — Homozygous escalation fires when effective_ref is None 🟠 HIGH

**File:** `services/insight_generators/base.py`  
**Functions:** `zygosity_adjust()`, `is_homozygous_reference()`

**Problem:**  
When `effective_ref is None` (ref allele unknown — Phase 2.5 correction didn't find a match), `is_homozygous_reference(genotype, ref_allele=None)` returns `False`. This causes the `zygosity_adjust` flow to fall through to the `else` branch (interpreted as "homozygous non-reference") and **escalate risk by 1 step**.

Example: Variant `rs12345` with genotype `AA`. If the effective_ref is `A` (unknown at processing time), the user is actually homozygous reference (wild-type). But `zygosity_adjust` sees `effective_ref=None`, can't classify, escalates to `moderate` instead of `low`.

This generates false-positive elevated risks for thousands of common variants where the user is genuinely wild-type.

**Fix:**  
Add an explicit guard in `zygosity_adjust`:
```python
if ref_allele is None:
    # Cannot determine zygosity without reference — return baseline unchanged
    return level
```

---

### BUG-08 — Drug gene-map matching has no benign filter 🟠 HIGH

**File:** `services/insight_generators/drug_response.py`  
**Function:** `generate_drug_responses()`

**Problem:**  
The rsid-map path calls `is_clinvar_benign()` correctly. But the gene-map path (matching to pharmacogenes like CYP2D6, CYP2C19, VKORC1) does **not** filter benign variants. Any variant in a pharmacogene — including purely intronic or synonymous variants with `likely_benign` classification — generates a drug response insight.

**Consequence:** Users with common benign CYP2D6 haplotype markers may see "Poor Metabolizer" warnings for drugs when their functional status is actually normal.

**Fix:**  
In the gene-map matching loop in `generate_drug_responses`:
```python
# Add before generating drug insight from gene match:
profile = profiles.get(variant.rsid)
if profile and profile.is_benign:
    continue
```

---

### BUG-09 — Carrier status uses marker ref_allele instead of annotation-corrected ref 🟡 MEDIUM

**File:** `services/insight_generators/carrier.py`  
**Function:** `generate_carrier_status()`, `_classify_carrier_status()`

**Problem:**  
`generate_carrier_status` calls `get_ref_allele(variant)` which reads `variant.ref_allele` from the in-memory `VariantLite` object. For consumer CSV uploads, the initial `ref_allele` is set to `genotype[0]` — often just the first base of the genotype, not the true reference allele.

Phase 2.5 corrects these in the DB, but the in-memory `VariantLite` objects are not refreshed after correction. Other generators use `_get_effective_ref_allele()` which checks the annotation-derived ref first — carrier generator does not.

**Impact:** Carrier classification errors (e.g., classifying a genuine carrier as "affected" or vice versa) for variants where the stored ref_allele is wrong.

**Fix:**  
Replace `get_ref_allele(variant)` with `profile.effective_ref` in `_classify_carrier_status` calls, where `profile = profiles.get(variant.rsid)`.

---

### BUG-10 — Non-deterministic gene assignment for multi-gene rsids 🟡 MEDIUM

**File:** `services/analysis_service.py`  
**Function:** `_build_rsid_gene_map()`

**Problem:**  
The ClinVar-based gene lookup uses:
```python
SELECT DISTINCT ON (rsid) rsid, gene FROM clinvar_variants
```
`DISTINCT ON` without `ORDER BY` is **non-deterministic** in PostgreSQL. For RSIDs appearing in multiple ClinVar records with different gene assignments (overlapping genes, alternative transcripts), the selected gene is arbitrary and varies across runs.

**Fix:**
```python
# Add ORDER BY to make it deterministic — prefer most common gene
SELECT DISTINCT ON (rsid) rsid, gene FROM clinvar_variants
ORDER BY rsid, gene  -- or ORDER BY rsid, clinical_significance DESC for clinical priority
```

---

### BUG-11 — Personality and Sports get meaningless category values from auto-categorizer 🟡 MEDIUM

**Files:** `services/auto_categorizer.py`, `services/insight_generators/personality.py`, `services/insight_generators/sports.py`

**Problem:**  
`_match_condition_keyword()` sets `data.setdefault("category", keyword.capitalize())` and `data.setdefault("trait", f"{gene} variant")` for gene-type mappings via `_match_gene_list()`.

Results in the dashboard:
- Sports category = "Muscle", "Endurance", "Myopathy" — not performance categories
- Personality trait = "SLC6A4 variant", "DRD2 variant" — not trait names
- Physical trait = same generic pattern

**Fix:**  
1. Add a `trait_name_override` field to the CategoryRule `mapping_data_template` JSON (per-rule custom name)
2. Or, add gene→trait-name lookup tables (especially for known PGx/behavior genes)
3. Short-term: add a cleanup post-processor that maps "gene variant" to "Gene Variant" at display time

---

## 3. Scoring Engine Issues

---

### BUG-12 — MIN_WEIGHT_FLOOR prevents ClinVar Pathogenic from scoring as Pathogenic 🟠 HIGH

**File:** `services/scoring_engine.py`  
**Function:** `_calculate_composite()`

**Problem:**  
`MIN_WEIGHT_FLOOR = 0.40`. When a variant has only ClinVar local data (weight=0.30) with pathogenic classification (raw score=0.95):

```
composite = 0.95 × 0.30 / max(0.30, 0.40) = 0.95 × 0.30 / 0.40 = 0.7125
→ classified as likely_pathogenic, not pathogenic
```

A ClinVar 5-star Pathogenic assertion is clinical gold standard. Downgrading it to `likely_pathogenic` due to missing computational tools contradicts clinical interpretation guidelines (ACMG 2015: ClinVar Pathogenic = PVS1 level evidence).

**Fix options:**
1. Add a "ClinVar override" rule: if ClinVar pathogenic with ≥2 star review and no conflicting benign evidence → classify as `pathogenic` regardless of composite score
2. Lower `MIN_WEIGHT_FLOOR` to 0.25 for ClinVar-only variants
3. Add `authoritative_classification` field to scoring result that prioritizes ClinVar LP/P assertions

---

### BUG-13 — Only health generator passes pathogenicity_score to assess_risk_level 🟡 MEDIUM

**File:** `services/insight_generators/` — all non-health generators  
**Function:** `assess_risk_level()`

**Problem:**  
`assess_risk_level(genotype, risk_multiplier, ref_allele, pathogenicity_score=None)` has composite-score-based logic only used when `pathogenicity_score` is passed. All generators except `health.py` call it with `pathogenicity_score=None`, meaning they fall back to multiplier-only risk assessment.

This means the scoring engine's work (AlphaMissense, ClinVar local evidence) is computed but not used for risk level assignment in nutrition, sports, cognitive, personality, wellness, methylation, detox panels.

**Fix:**  
Pass `profiles[rsid].composite_score` as `pathogenicity_score` in the `generate_from_maps` call for all generators, or let `generate_from_maps` pass it automatically from the VariantProfile.

---

### BUG-14 — Scoring engine ClinVar dedup checks on 'found' before dedup 🟢 LOW

**File:** `services/scoring_engine.py`  
**Function:** `_aggregate()`

**Clarification of a potential bug:**  
The dedup logic `if 'clinvar' in evidences and 'clinvar_local' in evidences: drop clinvar_local` only fires when both sources return non-None evidence. Since `_score_clinvar()` returns `None` for `found: false`, the remote API's `found: false` response does NOT trigger the dedup.

So this is not actively harmful in the current setup. However, if the remote ClinVar API is re-enabled in the future and returns `found: true` for a variant, the local ClinVar data (which may have more expanded star-review data) would be silently dropped. The dedup should instead compare star review ratings and keep the higher-quality source.

---

## 4. Analysis Pipeline Bugs

---

### BUG-15 — 1000G ETL pointed at wrong directory 🔴 CRITICAL

**File:** `services/thousand_genomes_etl.py` line 38  
**Status:** FIXED in this session

**Problem:**  
The default `_DATA_DIR` was `data_sources/ensembl/homo_sapiens/variation/vcf_vep/` but the actual file is at `data_sources/1000G/1000GENOMES-phase_3.vcf.gz`. ETL would find no VCF file → `thousand_genomes_variants` table empty → no population frequency data available.

Note: The file uses a **CSI index** (`.csi`) not a TBI index. It cannot be queried via `pysam.TabixFile`. The ETL correctly reads it as a plain gzip stream — CSI is only needed for bcftools random-access, not for the sequential ETL scan.

**Fix applied:** Changed `_DATA_DIR` default to `data_sources/1000G`.

---

### BUG-16 — gnomAD CADD file is GRCh38 but user data is GRCh37 🔴 CRITICAL

**File:** `services/gnomad_cache.py`  
**Manifest:** `gnomad_cache_meta.json` shows `variant_count: 0`

**Problem:**  
The gnomAD CADD file (`gnomad.genomes.r4.0.indel_inclAnno.tsv.gz`) header states `##CADD GRCh38-v1.7`. Consumer DNA chip files (23andMe, AncestryDNA) provide positions on **GRCh37/hg19**. The cache builder compares positions from `genetic_markers` (GRCh37) against the CADD file positions (GRCh38) — they never match, so cache is always empty.

**Fix:**  
Download the GRCh37 version:  
```
https://krishna.gs.washington.edu/download/CADD/v1.6/GRCh37/gnomad.genomes.r2.1.1.snv_inclAnno.tsv.gz
```
Replace `gnomad.genomes.r4.0.indel_inclAnno.tsv.gz` with this file (and regenerate the `.tbi` index), then delete the SQLite cache to force rebuild.

---

### BUG-17 — Resume phase detection broken for Phase 3 🟡 MEDIUM

**File:** `services/analysis_service.py`  
**Function:** `_completed_phases`, `process_analysis()`

**Problem:**  
The `_completed_phases` dict maps phase detection keys to progress percentages:
```python
_completed_phases = {
    'gene_mapping': 5,
    'annotating': 30,
    'enriching_bigquery': 90,  # ← WRONG KEY
    'generating_insights': 100
}
```

But the actual `current_step` value written to the DB when Phase 3 starts is `'enriching_data'`, not `'enriching_bigquery'`.

**Result:** On resume from a paused analysis that completed Phase 3, the check `if _completed_phases.get('enriching_data', 0)` returns 0 → Phase 3 always re-runs unnecessarily (but doesn't corrupt data since Phase 3 is currently a no-op with BigQuery disabled).

**Fix:**
```python
_completed_phases = {
    ...
    'enriching_data': 90,  # matches what's actually written
    ...
}
```

---

### BUG-18 — annotation_status never promoted to 'completed' 🟢 LOW

**File:** `services/shared_annotation_service.py`

**Problem:**  
711,792 / 714,586 annotations (99.6%) remain at status `partial` indefinitely. The service never updates status to `completed` even when all enabled sources have been populated.

**Impact:** Informational only; `get_existing_annotations()` correctly includes partial annotations. But the status field cannot be used for data quality monitoring.

**Fix:**  
After backfill: add a status update that marks annotation as `completed` when all `is_enabled=True` sources in `annotation_source_configs` have been populated. Check after each backfill run.

---

## 5. Data Quality Issues

---

### DQ-01 — Auto-categorizer creates mappings with garbage condition names 🟠 HIGH

**File:** `services/auto_categorizer.py`  
**Function:** `_clean_condition()`

**Problem:**  
AutoCategorizer filters `not provided` and `not specified` as primary condition values but still creates mappings when these appear alongside other ClinVar pipe-delimited fields. Result in live DB:

```sql
SELECT data->>'condition', COUNT(*) FROM variant_mappings
WHERE category = 'health' AND data->>'condition' IN ('not provided', 'not specified')
GROUP BY 1;
-- Result: 'not provided': 248, 'not specified': 18
```

Users see "not provided" as a health risk condition name. Additional generic conditions also present:
```
'Inborn genetic diseases': 95 rows
'Hereditary cancer-predisposing syndrome': many rows
'Cardiovascular phenotype': many rows
```

**Fix:**
1. Add to `_clean_condition()` skip-list: `'inborn genetic diseases'`, `'cardiovascular phenotype'`, `'hereditary cancer-predisposing syndrome'`, `'hereditary disease'`, `'see cases'`, `'not applicable'`, `'complex'`
2. Run cleanup SQL to remove existing garbage entries:
```sql
DELETE FROM variant_mappings
WHERE category IN ('health', 'carrier', 'rare_mutations')
  AND (
    (map_type = 'rsid' AND data->>'condition' ILIKE ANY 
      ARRAY['not provided', 'not specified', 'not applicable', 'inborn genetic%', 'see cases', 'complex'])
    OR data->>'condition' IS NULL
  );
```
3. Re-run AutoCategorizer for affected categories

---

### DQ-02 — 1,114 health rsid mappings have conflicting-classification significance 🟡 MEDIUM

**File:** `services/auto_categorizer.py`  
**Function:** `_match_condition_keyword()`

**Problem:**  
Condition-keyword rules don't filter `conflicting classifications of pathogenicity` significance — only `benign` is excluded. So 1,114 health rsid mappings were created from ClinVar entries with conflicting evidence, assigned `risk_multiplier=1.3`.

These represent variants where some submitters claim pathogenic and others claim benign. Presenting these as health risks (even low-level) may be misleading.

**Fix:**  
Either:
1. Add `conflicting%` to the exclusion list in `_match_condition_keyword()` for the health category
2. Or set `risk_multiplier=1.0` for conflicting significance entries and only show them in an "Uncertain" section
3. Ensure the frontend shows clinical_significance on health risk cards so users can see "Conflicting evidence"

---

### DQ-03 — carrier_status dedup allows multiple conditions per gene 🟢 LOW

**File:** `services/insight_generators/carrier.py`

**Problem:**  
Carrier status deduplicates by `condition` (disease name). This means a user can have 50+ carrier entries for variants in the same gene (e.g., 20 CFTR variants → 20 cystic fibrosis entries from different ClinVar records).

**Fix:**  
Add secondary dedup by gene: keep only the highest-priority entry per (gene, condition) pair. Or dedup strictly by gene for known single-disease genes.

---

## 6. Architectural Gaps

---

### ARCH-01 — panel_marker_configs → variant_mappings bridge missing 🔴 CRITICAL

See BUG-04. This is one of the most impactful architectural issues. The curated panel represents expert curation effort that's completely bypassed by the analysis engine.

**Recommended Fix:**
Create a management command to bridge the two tables:
```python
# scripts/sync_panel_to_registry.py
# For each panel_marker_config not in variant_mappings:
#   - If category is health/rare_mutations: create rsid-type mapping with panel-appropriate template
#   - If category is drug: create drug-appropriate mapping with gene or rsid key
#   - Set is_auto_discovered=False (manually curated)
```

---

### ARCH-02 — BigQuery enrichment disabled but code adds latency 🟡 MEDIUM

**File:** `services/analysis_service.py`, Phase 3

BigQuery has been disabled. The Phase 3 code still runs, opens service connections, checks feature flags, and logs progress — all for 0 results. 

**Fix:**  
Add a config check at the top of Phase 3: `if not settings.BIGQUERY_ENABLED: skip`. Or gate all Phase 3 code behind a single `HAS_BIGQUERY_SOURCES` computed config value.

---

### ARCH-03 — No population frequency for zygosity baseline adjustment 🟡 MEDIUM

**File:** `services/insight_generators/base.py`  
**Function:** `generate_from_maps`

When generating insights, variants with the **risk allele** as the **common allele** (e.g., the "risk" variant has global AF=0.60) should probably not be flagged as high risk for homozygous carriers (since being homozygous is actually the population norm). Currently only the registry `risk_multiplier` and pathogenicity score factor in.

**Fix:**  
Use `profile.population_frequency` in `assess_risk_level`: if `freq > 0.50`, treat the variant as the common allele and adjust baseline risk downward regardless of ClinVar significance.

---

### ARCH-04 — dashboard_cache invalidation not triggered on insight regeneration 🟡 MEDIUM

**File:** `backend/api/analysis_routes.py`

After `POST /api/analysis/regenerate-insights` completes, the old dashboard cache entry may still be returned to the user until the fingerprint changes (based on `updated_at` of the analysis). If `updated_at` isn't explicitly bumped after Phase 4 completes, the user sees stale data even after regeneration.

**Fix:**  
After Phase 4 insight generation completes, explicitly update `analysis.updated_at = func.now()` and/or DELETE the `dashboard_cache` entry for that analysis ID.

---

### ARCH-05 — Job logs column has no size limit 🟢 LOW

**File:** `db/models.py` — `GeneticAnalysis.job_logs` (JSONB array)

For long analyses, the `job_logs` array accumulates thousands of timestamped entries and can reach hundreds of MB per job. This slows down all queries that touch the `genetic_analyses` table.

**Fix:**  
Either:
1. Store logs in a separate `analysis_logs` table with one row per entry
2. Or rotate logs in the JSONB array to keep only the last N entries: `job_logs[-1000:]`

---

## 7. Frontend Issues

---

### FE-01 — Hardcoded variant descriptions are incomplete 🟢 LOW

**File:** `frontend/src/components/categories/HealthPanel.tsx`  
**Function:** `getVariantDescription()`

**Problem:**  
Only 3 variants (APOE-ε4, rs7903146, rs1801133) have hardcoded human-readable descriptions. All other 2000+ health rsids show generic "variant of interest in [condition]" messages.

**Fix:**  
Move variant descriptions to `variant_mappings.data` JSON (add a `description` field) or pull from ClinVar annotation (already available in `shared_variant_annotations`). Remove hardcoded switch/case.

---

### FE-02 — No loading state for dashboard-data fetch 🟢 LOW

**File:** `frontend/src/components/Dashboard.tsx`

If `dashboard-data` is slow (first load or cache miss), some panels show blank content with no skeleton/loading indicator.

---

## 8. Fix Priority Order

Recommended fix sequence by clinical impact and effort:

| Priority | Bug ID | Title | Effort | Impact |
|----------|--------|-------|--------|--------|
| 1 | BUG-16 | gnomAD CADD is GRCh38, data is GRCh37 | Medium (download GRCh37 file) | CRITICAL — CADD/SIFT/PolyPhen never annotate |
| 2 | BUG-01 | gnomAD scoring weight dead (blocked on fix above) | Low (run ETL after #1) | CRITICAL — 40% dead scoring weight |
| 3 | BUG-15 | 1000G ETL wrong path | ✅ FIXED | CRITICAL — 1000G table was always empty |
| 4 | BUG-04/ARCH-01 | panel_marker_configs disconnected | Medium | CRITICAL — curated BRCA/TP53 ignored |
| 5 | BUG-05 | uncommon_mutations always 0 | Low (blocked on #1–2) | CRITICAL |
| 6 | BUG-07 | Homozygous escalation with no ref | Low (add guard) | HIGH — false positive risks |
| 7 | BUG-06 | zygosity_adjust alias gaps | Very low (5 lines) | HIGH — no adjustment for these variants |
| 8 | DQ-01 | Garbage condition names | Low (cleanup SQL) | HIGH — UI shows 'not provided' |
| 9 | BUG-08 | Drug benign filter missing | Low (5 lines) | HIGH — phantom drug responses |
| 10 | BUG-02 | AlphaMissense coordinate check | Low (investigation) | HIGH — 0.17% hit rate |
| 11 | BUG-12 | ClinVar pathogenic scoring floor | Medium | HIGH — misclassifies gold standard |
| 12 | BUG-10 | Non-deterministic gene assignment | Very low (add ORDER BY) | MEDIUM |
| 13 | BUG-17 | Resume step name mismatch | Very low (rename key) | MEDIUM |
| 14 | BUG-13 | pathogenicity_score not passed to non-health generators | Low | MEDIUM |
| 15 | BUG-09 | Carrier ref_allele uses uncorrected value | Low | MEDIUM |
| 16 | DQ-02 | Conflicting classifications in health | Low | MEDIUM |
| 17 | BUG-11 | Meaningless sports/personality names | Medium | MEDIUM — UX quality |
| 18 | ARCH-04 | Cache invalidation after regeneration | Low | MEDIUM |
| 19 | BUG-03 | Ensembl gene_symbol 0.2% | Investigation needed | LOW — gene matching works via fallback |
| 20 | DQ-03 | Carrier CFTR overcount | Low | LOW |
| 21 | ARCH-02 | BigQuery dead code | Very low | LOW |
| 22 | ARCH-05 | Job logs unbounded size | Medium | LOW |
