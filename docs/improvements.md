# Bugs, Shortcomings & Improvement Plan

> Full audit completed 2026-03-18. Covers all backend services, DB schema, insight generators, annotation pipeline, variant mapping system, and frontend integration.

---

## Table of Contents

1. [Critical Bugs (False Positive Insights)](#1-critical-bugs)
2. [Variant Mapping & Auto-Categorizer Flaws](#2-variant-mapping-flaws)
3. [Scoring Engine & Risk Assessment Issues](#3-scoring-engine-issues)
4. [Data Quality Issues](#4-data-quality-issues)
5. [Architecture Problems](#5-architecture-problems)
6. [Dead Code & Cleanup](#6-dead-code)
7. [Performance Issues](#7-performance-issues)
8. [Frontend Issues](#8-frontend-issues)
9. [Recommended Improvements](#9-recommended-improvements)

---

## 1. Critical Bugs (False Positive Insights)

### BUG-01: No Risk Allele in Variant Mappings — Root Cause of False Positives

**Severity: CRITICAL**

The variant_mappings table stores rsid → condition associations but **never stores which allele is the risk allele**. The mapping data looks like:

```json
{"condition": "Type 2 Diabetes", "risk_multiplier": 1.4}
```

This means the system knows *which variant position* is associated with a disease, but not *which allele at that position* causes the risk. The only defense is `is_homozygous_reference()` — but this requires a known reference allele, which is unavailable for 80% of markers (see BUG-04).

**Impact**: A user with rs7903146 CC (homozygous reference = no risk) could be flagged for Type 2 Diabetes if the ref allele can't be resolved from annotations.

**Fix**: Add `risk_allele` and `protective_allele` fields to variant_mappings. The `generate_from_maps()` function should verify the user's genotype contains the risk allele before generating an insight.

---

### BUG-02: Auto-Categorizer Generates Mass Low-Quality Mappings

**Severity: CRITICAL**

The auto-categorizer (`auto_categorizer.py`) generates ~20,000 variant mappings from ClinVar with severe quality problems:

1. **Uniform risk_multiplier=3.0** for ALL "Pathogenic" variants regardless of disease penetrance, effect size, or population frequency. A rare Mendelian disease variant gets the same weight as a common risk factor.

2. **Same condition string populates ALL fields**: `trait`, `domain`, `metric`, `nutrient`, `category` are all set to the disease name (e.g., "Galactosylceramide beta-galactosidase deficiency" as a nutrient name).

3. **Garbage condition names leak through**: "See cases", "not provided", "not specified" appear as health conditions.

4. **Variants spread across ALL categories**: A ClinVar pathogenic variant for "Cardiomyopathy" creates mappings in health, nutrition, sports, wellness, methylation, personality, cognitive, detox, physical — because the auto-categorizer doesn't filter by category relevance.

5. **Conflicting classifications treated as pathogenic**: ClinVar "Conflicting classifications of pathogenicity" contains the substring "pathogenic" and was previously matched by the `clinvar_significance = 'Pathogenic'` rule. Although there's now a `~ILIKE 'conflicting%'` filter, variants with *multiple* ClinVar entries (some pathogenic, some conflicting) can still slip through via `DISTINCT ON (rsid)`.

**Evidence from DB** (analysis 83):
- rs1042522 (TP53): ClinVar says "Benign" + "Conflicting" → flagged as **Li-Fraumeni syndrome, HIGH risk**
- rs1008642 (CAV3): ClinVar says "Pathogenic" + "Benign/Likely benign" → flagged as **Distal myopathy, HIGH risk**
- rs1024611 (CCL2): ClinVar says "Uncertain significance" → flagged as **Coronary Artery Disease** (via gene map)

**Fix**: 
- Validate that the variant's pathogenic classification applies specifically to the allele the user carries
- Don't assign the same condition across all 12 categories — use disease ontology to determine relevant categories
- Require ≥2-star ClinVar review status for auto-categorization
- Filter out conditions like "not provided", "See cases", "not specified"
- Cap risk_multiplier based on ClinVar evidence strength: 1-star=1.2, 2-star=1.5, 3-star=2.0, 4-star=3.0

---

### BUG-03: Carrier Status False "Affected" from D/I Indel Code Misinterpretation

**Severity: HIGH**

Consumer CSV genotypes use D/I codes for indels: DD = deletion/deletion, II = insertion/insertion, DI = heterozygous. The system interprets these by comparing ref and alt allele lengths to determine if D=ref or D=alt.

**Problem**: When `alt_alleles = 'N'` (placeholder, 11,610 markers), the function `indel_d_is_ref(ref='TT', alt='N')` compares `len('TT')=2 > len('N')=1` and concludes it's a "deletion variant" — treating DD as homozygous alternate = "affected".

**Evidence from DB** (analysis 83):
- rs267608531 (Autism X-linked): genotype=DD, ref=TT, alt=N → classified as **affected**
- rs398124103 (Duchenne muscular dystrophy): genotype=DD, ref=CC, alt=N → classified as **affected**
- rs886039136 (Fabry disease): genotype=DD, ref=GG, alt=N → classified as **affected**

All these are false positives caused by `alt='N'` being interpreted as a real single-nucleotide allele.

**Fix**: Treat `alt_alleles = 'N'` as unknown (same as None). `indel_d_is_ref()` should return None when either allele is 'N', causing the system to classify as 'carrier' (conservative) rather than 'affected'.

---

### BUG-04: 80% of Markers Have ref_allele == alt_alleles (Ambiguous)

**Severity: HIGH**

Database query shows **582,301 out of 731,703 markers (79.6%)** have `ref_allele == alt_alleles`. This happens because the consumer CSV uploader (`variant_uploader.py`) sets `ref_allele = genotype[0]` and `alt_alleles` to the other allele — but for homozygous genotypes (AA, CC, etc.), both are the same letter.

**Impact**: When ref == alt:
- `_get_effective_ref_allele()` correctly returns None (it filters this case)
- But then `is_homozygous_reference()` can't determine if user is hom-ref or hom-alt
- `generate_from_maps()` skips the hom-ref filter and proceeds to insight generation
- The user may be flagged for a disease where they carry ONLY the reference allele

The `_correct_ref_alleles()` phase is supposed to fix this using authoritative annotation sources, but the log shows "ref_allele correction: all markers already correct" — meaning either annotations lack ref data or the correction logic has bugs.

**Fix**:
- During Phase 2 annotation, when ClinVar/Ensembl/gnomAD provide authoritative ref alleles, update `genetic_markers.ref_allele` to the true reference
- In insight generation, when ref allele is unavailable, require annotation confirmation before flagging

---

### BUG-05: Scoring Engine Overrides ClinVar "Conflicting" to "Likely Pathogenic"

**Severity: HIGH**

The rare mutation generator uses the scoring engine's `composite_score` to upgrade uncertain/conflicting ClinVar classifications:

```python
if clinical_significance in ('uncertain', 'conflicting') and composite >= 0.60:
    if score_classification in ('pathogenic', 'likely_pathogenic'):
        clinical_significance = 'likely_pathogenic'
```

**Problem**: Computational predictors (CADD, PolyPhen, SIFT) score protein structure impact, NOT clinical pathogenicity. A variant can be computationally "damaging" but clinically benign (common polymorphism in a tolerated region). The scoring engine's composite can reach 0.60 from CADD + AlphaMissense alone without any clinical evidence.

**Evidence from DB**: 6 variants with ClinVar "Conflicting" were upgraded to "likely_pathogenic" in rare_mutations (rs148247227, rs41284962, rs139372534, rs150555106, rs2230892, rs45450893).

**Fix**: The scoring engine should NEVER override ClinVar clinical classifications. Computational scores should supplement, not replace, clinical curation. The rare mutation generator should only report variants as "likely_pathogenic" if ClinVar explicitly says so.

---

### BUG-06: Allele Mismatch Not Checked in rsid Map Matching

**Severity: HIGH**

When `generate_from_maps()` finds a variant in the rsid_map, it checks:
1. Is user homozygous reference? (skip)
2. Is ClinVar benign? (skip)

But it **never checks if the user's alleles match the risk allele for the specific condition**. The Ensembl allele_string might say "G/A" (ref=G, alt=A) and the user has G/C — a completely different variant at the same position — but the system would still flag them.

**Example**: rs148247227 (RBP3) — Ensembl says alleles are C/T, but the user has GG. The user's G alleles don't match either C (ref) or T (alt). Yet it's flagged as "likely_pathogenic".

**Fix**: For rsid matches, verify that the user's genotype contains at least one of the known alternate alleles from annotation data. Strand-flip correction is already implemented in rare_mutations.py but NOT in `generate_from_maps()`.

---

## 2. Variant Mapping & Auto-Categorizer Flaws

### FLAW-01: One-Size-Fits-All Template for All Categories ✅ FIXED

~~The auto-categorizer fills the same fields (`trait`, `domain`, `metric`, `nutrient`, `category`) with the disease name regardless of which dashboard category the mapping targets.~~ Now uses `_populate_category_fields()` which sets only the semantically relevant dedup field (e.g. `nutrient` for nutrition, `domain` for cognitive) to the condition name, and others to the gene label.

### FLAW-02: No ClinVar Review Status Filtering ✅ FIXED

~~The auto-categorizer uses `clinical_significance ILIKE '%Pathogenic%'` without checking `review_status`.~~ Now filters out entries with "no assertion criteria provided", "no classification provided", empty, and "-" review statuses.

### FLAW-03: PanelMarkerConfig vs VariantMapping Redundancy

Two tables serve overlapping purposes:
- `panel_marker_configs`: Panel-specific marker associations (admin UI)
- `variant_mappings`: Category-level rsid/gene → insight data

The carrier generator uses `variant_mappings` for its rsid_map. The relationship between these two tables is unclear — `panel_marker_configs` appears to be a UI layer that doesn't feed into insight generation.

### FLAW-04: Gene Map Matching Too Broad

When a variant maps to a gene via Ensembl/ClinVar, and that gene appears in the gene_map, the system generates an insight. But the gene_map only knows "CYP2D6 → drug response" — it doesn't know which variants in CYP2D6 are gain-of-function vs loss-of-function vs neutral. A synonymous variant in CYP2D6 should not trigger a drug response warning.

The code partially addresses this by filtering `impact in ('HIGH', 'MODERATE')`, but many missense variants in well-known genes are benign (e.g., rs1135840 in CYP2D6 is benign).

---

## 3. Scoring Engine & Risk Assessment Issues

### SCORE-01: ClinVar Local and ClinVar API Double-Counted

Both `clinvar` and `clinvar_local` sources have weight 0.30 each (total 0.60). When both sources are available for a variant, ClinVar's opinion counts for 60% of the score — which is intentional as ClinVar is the gold standard. However, they're measuring the SAME underlying data (ClinVar's database). When they agree, the variant gets an inflated score. When they disagree (e.g., local has newer data), the composite becomes unpredictable.

**Fix**: Use `max(clinvar_score, clinvar_local_score)` rather than summing both, or deduplicate ClinVar evidence.

### SCORE-02: risk_multiplier Has No Evidence Basis

Manual health mappings use risk_multiplier values like 1.2, 1.3, 1.4, 1.5. These appear to be arbitrary guesses rather than odds ratios from GWAS literature. The mapping for rs7903146 (TCF7L2) uses 1.4, but the actual per-allele odds ratio from GWAS is ~1.4 for heterozygous and ~2.0 for homozygous — suggesting the value is coincidentally close but not derived from evidence.

Auto-categorized mappings uniformly use 3.0 for "Pathogenic" — treating all pathogenic variants equally regardless of penetrance, which ranges from <1% to >90% across different diseases.

### SCORE-03: assess_risk_level Thresholds Are Coarse

```python
if risk_multiplier >= 2.0: base = 'high'
elif risk_multiplier >= 1.2: base = 'moderate'
elif risk_multiplier <= 0.8: base = 'low'
else: base = 'average'
```

The gap between "moderate" (1.2x) and "high" (2.0x) is too wide. A 1.9x risk multiplier is classified as "moderate", while 2.0x jumps to "high". Also, the range 0.8–1.2 maps to "average" which is appropriate for neutral variants but the boundaries are arbitrary.

### SCORE-04: zygosity_adjust Without ref_allele Falls Through Silently

When `ref_allele=None` (80% of cases), `zygosity_adjust()` correctly avoids escalating, but it also doesn't de-escalate homozygous reference variants. Since the code can't distinguish hom-ref from hom-alt without a ref allele, it preserves the baseline — meaning the user gets the "heterozygous" level regardless of their actual genotype.

---

## 4. Data Quality Issues

### DATA-01: ✅ FIXED — gnomAD PG Table Is Empty (Tabix Fallback Added)

All three gnomAD lookup paths now fall back to tabix files when PG is empty:
- Single lookup (`lookup()`): PG → SQLite cache → tabix (added in prior session)
- Position batch (`lookup_batch()` with coords): PG → tabix (added in prior session)  
- rsid batch (`lookup_batch()` with rsids): PG → resolve coords from genetic_markers → tabix (added this session)

The job logs show `gnomAD PG: empty — run ETL`. The gnomAD ETL has not been run, meaning:
- gnomAD data comes only from the SQLite cache (419 variants) and the CADD TSV tabix file
- Backfill runs for ALL 609K variants but finds only 2 matches (0.0003%)
- 143 seconds wasted querying an empty table
- Population frequencies from gnomAD are essentially unavailable

### DATA-02: Ensembl VEP Cache Is Small

Only 712,732 variants cached vs 609,346 user variants. The cache hit rate depends on rsid overlap. For variants not in the cache, gene/consequence data comes only from ClinVar rsid→gene map (30,340 matches) and Ensembl local gene lookup (333,894 matches). ~40% of variants have no gene assigned.

### DATA-03: Genome Build Inconsistencies

Different data sources use different genome builds:
- User data: Typically GRCh37 (consumer arrays)
- ClinVar: Both GRCh37 and GRCh38 entries
- gnomAD CADD TSV: GRCh38
- gnomAD-tx: GRCh37
- Ensembl VEP VCFs: GRCh38
- 1000 Genomes: GRCh37

Position-based lookups can silently fail when builds don't match. The system has some liftover logic but no systematic build-aware matching.

### DATA-04: ✅ FIXED — Analysis Pipeline Required ETL for Full Data

**Problem**: Several analysis code paths silently returned empty data when PG was unpopulated (ETL not run):
1. `load_local_sources()` only checked `is_loaded` but didn't call `ensure_loaded()` for ClinVar, gnomAD, and 1000G — services skipped if not pre-loaded
2. `build_rsid_gene_map()` had no file fallback — gene map was empty when both `clinvar_variants` and `ensembl_genes` PG tables were empty
3. Gene-condition mappings (`gene_condition_source_id.txt`) and gene-level stats (`gene_specific_summary.txt`) were only consumed by ETL, never during direct-file analysis
4. When ClinVar fell back to `clinvar_direct`, results had empty `gene_conditions` and `gene_stats` fields

**Fixes applied** (4 files, 3 fixes):
- **Fix 1** (`local_annotation.py`): Added `ensure_loaded()` calls for ClinVar, gnomAD, and 1000G services when `is_loaded` is False
- **Fix 2** (`variant_loader.py`): Added Step 1b (ClinVar direct SQLite fallback for gene extraction) and Step 2b (Ensembl VEP cache fallback for gene symbols) to `build_rsid_gene_map()`
- **Fix 3** (`clinvar_direct.py` + `clinvar_local.py`): Added `_parse_gene_conditions()` and `_parse_gene_stats()` methods to `ClinVarDirectService` that parse local TSV files (5,123 gene→condition and 92,618 gene→stats entries). Wired into `clinvar_local.py` batch and single lookup fallback paths via `_enrich_direct_result()`

---

## 5. Architecture Problems

### ARCH-01: ✅ FIXED — analysis_service.py Was a God Object (1800+ LOC)

Split into 4 focused modules (567 + 290 + 530 + 250 ≈ 1637 total LOC):
- `analysis_service.py` (567 LOC) — orchestrator, dataclasses, progress/status
- `variant_loader.py` (290 LOC) — data loading, gene map, ref allele correction
- `annotation_coordinator.py` (530 LOC) — annotation reuse, local/remote, BQ enrichment
- `insight_dispatcher.py` (250 LOC) — insight generation, regeneration

The `ComprehensiveAnalysisService` class handles:
- Analysis orchestration
- Variant loading (Core SQL)
- Registry loading
- Gene map building
- Annotation coordination
- BigQuery enrichment
- Ref allele correction
- Insight generation dispatch
- Progress tracking
- Status persistence

This should be split into:
- `AnalysisOrchestrator` (pipeline coordination)
- `VariantLoader` (data access)
- `AnnotationCoordinator` (source management)
- `InsightDispatcher` (generator execution)

### ARCH-02: Service Proliferation for gnomAD ✅ FIXED

**Status**: Consolidated via `datasource_utils.py` shared module (210 LOC).

Full strategy-pattern rewrite was rejected — files have genuinely different responsibilities (lookup vs ETL vs cache). Instead, extracted duplicated code into `backend/services/datasource_utils.py`:

**Shared utilities created:**
- `safe_float()`, `safe_int()`, `clean_str()` — type coercion (was duplicated 7+ times)
- `parse_vcf_info()` — VCF INFO parser (was duplicated 6 times)
- `interpret_cadd()` — CADD PHRED interpretation (was duplicated 3 times)
- `load_known_rsids()`, `get_marker_fingerprint()` — DB queries (was duplicated 4 times each)
- `get_file_fingerprint()`, `get_multi_file_fingerprint()` — file fingerprinting
- `is_cache_valid()`, `save_cache_meta()`, `open_cache_db()`, `create_cache_db()`, `finalize_cache_db()` — SQLite cache lifecycle (was duplicated across 4 files, ~80 LOC each)

**Files updated (10 files, ~500 LOC removed):**
- `gnomad_local.py` — `interpret_cadd`
- `gnomad_cache.py` — `interpret_cadd` + all cache boilerplate (6 methods removed)
- `gnomad_bigquery.py` — `safe_float`/`safe_int` + absorbed `gnomad_backfill.py` (BackfillService merged)
- `clinvar_etl.py` — `parse_vcf_info` + `safe_float`
- `clinvar_direct.py` — all cache boilerplate (6 methods removed)
- `ensembl_vep_local.py` — all cache boilerplate (~130 LOC removed)
- `ensembl_vep_etl.py` — `parse_vcf_info`
- `thousand_genomes_etl.py` — `parse_vcf_info` + `safe_float`/`safe_int`
- `thousand_genomes_direct.py` — all cache boilerplate + `parse_vcf_info` + type helpers (6 class methods + 3 module functions removed)
- `admin_routes.py` — backfill import updated

**Files deleted:**
- `gnomad_backfill.py` — merged into `gnomad_bigquery.py`

### ARCH-03: No Dependency Injection for Services

Services create their own database connections via `async_session_factory()` scattered throughout the codebase. The `container.py` DI container exists but is largely unused — most services instantiate directly.

### ARCH-04: Auto-Categorizer Runs Separately from Analysis

The auto-categorizer is triggered via `POST /api/admin/auto-categorize` and writes to `variant_mappings`. The analysis service reads from `variant_mappings` at runtime. There's no version control or audit trail — if the auto-categorizer runs with bad rules, it silently corrupts the mapping table.

### ARCH-05: Annotation Data Shape Inconsistency

Different code paths produce different annotation data shapes:
- Fresh annotations: `annotation_data = {'rsid': ..., 'annotations': {...}, 'pathogenicity_score': {...}}`
- Cached annotations reconstructed from DB: `annotation_data = {'annotations': {'clinvar_local': <json>, 'ensembl': <json>, ...}}`

Generators must handle both shapes, leading to defensive `.get()` chains throughout.

### ARCH-06: Scoring Engine Runs During Annotation, Not During Insight Generation

Pathogenicity scores are computed during Phase 2 (annotation) and stored in `annotation_data['pathogenicity_score']`. If the scoring logic changes, all cached annotations must be re-scored. This should be a lazy computation during Phase 4 (insight generation) so it always uses the latest scoring logic.

---

## 6. Dead Code & Cleanup

### Dead Files (safe to remove)

| File | Reason |
|------|--------|
| `backend/services/health_insights.py` | Legacy mock with hardcoded data. Superseded by `insight_generators/health.py`. Registered in container.py but never retrieved. |
| `backend/services/drug_response.py` | Legacy mock. Superseded by `insight_generators/drug_response.py`. Registered in container.py but never retrieved. |
| `backend/api/test_routes.py` | Not imported or mounted in main.py. |
| `backend/utils/check_nulls.py` | Not imported anywhere. |
| `backend/utils/create_source_configs.py` | Not imported anywhere. |
| `backend/utils/test_incomplete.py` | Not imported anywhere. |

### Dead Registration in container.py

After removing the legacy files, also remove:
- `HealthInsights` and `DrugResponseAnalyzer` class registrations
- `HealthInsightsServiceInterface` and `DrugResponseServiceInterface` interfaces

### Root-Level Audit Files

The project root contains ~15 SQL/Python audit/test files (`audit.sql`, `audit2.sql`, ... `audit5.sql`, `audit_health.sql`, `check_ds.py`, `check_vep.py`, `test_fixes.py`, etc.). These are ad-hoc debugging scripts that should be moved to a `scripts/` directory or removed.

---

## 7. Performance Issues

### PERF-01: gnomAD Backfill Wastes 143 Seconds

The backfill scans all 609K variants against an empty gnomAD PG table, finding 0 results. Even with the SQLite cache (419 variants), only 2 matches are found. The system should check if gnomAD PG is empty and skip the entire PG lookup path.

### PERF-02: Annotation Lookup Takes 178 Seconds

Checking 609K variants against `shared_variant_annotations` takes 178 seconds (1,219 batches of 500). This is O(n) queries. A single `WHERE rsid = ANY(array)` batch query or a temporary table JOIN would be faster.

### PERF-03: 609K Variants Iterated 14 Times

Each of the 14 insight generators iterates ALL 609K variants. Most variants don't match any mapping. Building a pre-filtered set of "potentially interesting" variants (those with rsid in any mapping OR gene in any gene_map) would reduce iteration by ~97%.

### PERF-04: Phase 1 Gene Map Building Takes 57 Seconds

Building the rsid→gene map queries ClinVar PG and Ensembl local for all 609K rsids. This is rebuild on every analysis run. Caching this at the marker level (storing gene in `genetic_markers`) would make subsequent analyses instant.

---

## 8. Frontend Issues

### FE-01: No Allele Display in Dashboard

The dashboard shows condition + risk level + associated rsid, but NOT the user's genotype or the risk allele. Users cannot verify whether the system correctly matched their alleles.

### FE-02: No Confidence Indicator

Insights generated from auto-categorized mappings (source: "clinvar_auto") are displayed identically to manually curated mappings. There's no visual distinction between high-confidence evidence-based insights and auto-generated ones.

### FE-03: No Filtering by Clinical Evidence Level

Users cannot filter insights by ClinVar review status (stars), evidence strength, or population frequency.

---

## 9. Recommended Improvements (Priority Order)

### P0 — Must Fix (User-facing false positives)

1. **Add risk_allele to variant_mappings** and verify user genotype contains it before generating insights. For auto-discovered mappings, populate from ClinVar VCF alt allele. *(Partially addressed: BUG-06 allele verification in `generate_from_maps()` now checks annotation alt alleles at runtime, reducing the need for stored risk_allele. Full schema change still recommended for manual mappings.)*

2. ~~**Fix alt_alleles='N' interpretation** in `indel_d_is_ref()` — treat 'N' as unknown.~~ **✅ FIXED** — `indel_d_is_ref()` now treats 'N' as unknown alongside '-' and '.'.

3. ~~**Stop scoring engine from overriding ClinVar** — computational scores should inform confidence, not classification.~~ **✅ FIXED** — Removed the scoring engine override in `rare_mutations.py` that upgraded "conflicting"→"likely_pathogenic".

4. ~~**Clean up auto-categorizer garbage** — filter "not provided"/"See cases", require ≥1-star review status, don't spread disease names across irrelevant categories.~~ **✅ FIXED** — `_clean_condition()` rejects garbage values, `_match_significance()` and `_match_condition_keyword()` require minimum ClinVar review quality (filters out "no assertion criteria provided").

5. ~~**Add allele verification to generate_from_maps()** — before matching rsid_map, check that user's alleles intersect with known risk/alt alleles from annotation data.~~ **✅ FIXED** — Allele verification with strand-flip fallback added for non-indel genotypes.

### P1 — Should Fix (Accuracy improvements)

6. ~~**Deduplicate ClinVar scoring** — use max(clinvar, clinvar_local) not sum.~~ **✅ ALREADY FIXED** — `_aggregate()` in `scoring_engine.py` already drops clinvar_local when both sources present.

7. **Evidence-based risk_multiplier** — replace arbitrary multipliers with GWAS odds ratios where available, or use a standard 1.5x default. *(Data task — requires GWAS literature review per variant.)*

8. ~~**Gene map matching precision** — for gene-based matching, require the specific variant to have a functional consequence AND ClinVar pathogenic/likely_pathogenic significance for that gene-condition pair.~~ **✅ FIXED** — Gene-based matching now also checks `is_clinvar_benign()` before generating insights.

9. **Populate gnomAD PG** — run the ETL to fill the gnomAD table and get population frequency data for allele frequency filtering. *(ETL/data task.)*

10. **Build-aware position matching** — implement GRCh37↔GRCh38 liftover for position-based lookups. *(Complex — requires liftover chain files.)*

### P2 — Architecture Improvements

11. **Split analysis_service.py** into focused modules (orchestrator, loader, coordinator, dispatcher).

12. **Consolidate gnomAD services** (6 files → 1 with strategy backends).

13. **Move scoring to insight generation time** — compute pathogenicity scores during Phase 4, not Phase 2, so updated scoring logic applies without re-annotating.

14. ~~**Remove dead code** — 6 dead files, dead container registrations, root-level audit scripts.~~ **✅ FIXED** — 6 dead files removed, container registrations cleaned up.

15. ~~**Pre-filter variant iteration** — build a set of "interesting" rsids/genes before iterating 609K variants × 14 generators.~~ **✅ FIXED** — Pre-filtering in `_generate_comprehensive_insights()` reduces iteration to only variants matching any mapping or having ClinVar data.

### P3 — Nice to Have

16. **Show user genotype + risk allele in dashboard** — let users verify the match.

17. **Distinguish evidence quality in UI** — badge auto-discovered vs curated mappings, show ClinVar star rating.

18. **Version control variant_mappings** — audit trail for auto-categorizer runs.

19. **Cache rsid→gene at marker level** — store gene symbol in `genetic_markers` for instant lookup.

20. **Add ancestry sub-population granularity** — the 5-population model (AFR/AMR/EAS/EUR/SAS) is coarse; consider using 26-population gnomAD model.

---

## Additional Fixes Applied (2026-03-19)

### BUG-04: ref_allele correction now also fixes alt_alleles
**✅ FIXED** — `_correct_ref_alleles()` in `analysis_service.py` now also extracts and corrects `alt_alleles` from annotation sources (gnomAD, Ensembl, ClinVar) when the marker has `alt_alleles == ref_allele` (ambiguous consumer CSV data from homozygous genotypes).

### PERF-01: gnomAD PG skip when empty
**✅ FIXED** — `gnomad_local.py` now skips PG lookup (both individual and batch) when `_variant_count == 0`, saving ~143 seconds per analysis run.

### BUG-14: `info` Variable Referenced Before Assignment in `generate_from_maps()`
**✅ FIXED** — In `base.py`, the allele verification block (BUG-06) referenced `info.get('risk_allele')` before `info = rsid_map[rsid]` was executed. On the first loop iteration (or when the previous iteration didn't assign `info`), this caused an `UnboundLocalError`. If a previous iteration did assign `info`, the fallback silently read the *wrong* variant's mapping data. Fix: moved `info = rsid_map[rsid]` before the allele verification block.

### FE: X-linked hemizygous interpretation
**✅ FIXED** — `VariantDetailDialog.tsx` now detects X-chromosome variants and single-allele genotypes, displaying "Hemizygous" instead of "Homozygous Alternate" with appropriate messaging.
