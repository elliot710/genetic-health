# Improvements & Known Issues

> Audit date: 2025  
> Coverage: Backend services, insight generators, database schema, frontend panels  
> Priority levels: 🔴 Critical · 🟠 High · 🟡 Medium · 🔵 Low / Info

---

## Table of Contents

1. [Critical Logical Errors](#1-critical-logical-errors)
2. [High Priority Bugs](#2-high-priority-bugs)
3. [Medium Priority Issues](#3-medium-priority-issues)
4. [Database Schema Issues](#4-database-schema-issues)
5. [DRY Violations](#5-dry-violations)
6. [Separation of Concerns](#6-separation-of-concerns)
7. [Architecture Concerns](#7-architecture-concerns)
8. [Frontend Issues](#8-frontend-issues)
9. [Dead / Unused Code](#9-dead--unused-code)
10. [Data Observations](#10-data-observations)

---

## 1. Critical Logical Errors

### 1.1 🔴 Indel genotypes bypass allele verification entirely

**File:** `backend/services/insight_generators/base.py` — `generate_from_maps()`  
**Impact:** Users are flagged for conditions associated with indel variants regardless of whether their actual alleles match the risk allele.

```python
# Only SNPs get allele-verified. Indels (II/DD/DI/ID) are added on rsid presence alone.
if genotype and not is_indel_genotype(genotype):
    ann_alt = get_annotation_allele_parts(annotation_result)[1]
    if ann_alt in alleles:  # User carries risk allele — OK
        create_insight = True
    else:
        continue  # SNP allele mismatch — correctly skipped
# ↑ But if is_indel_genotype() returns True, this whole block is skipped
# → indel rsid match always proceeds
```

**Fix:** Implement allele verification for indels using the D/I → ref/alt interpretation already present in `is_homozygous_reference()`. If the user is `II` (insertion/insertion) and the risk allele is `D` (deletion), skip the insight.

---

### 1.2 🔴 `risk_allele` field missing from all variant_mappings — fallback silently disabled

**File:** `backend/services/insight_generators/base.py` — line ~823  
**DB observation:** `SELECT count(*) FROM variant_mappings WHERE data->>'risk_allele' IS NOT NULL` → **0 rows**

When annotation data has no allele information (e.g. local ClinVar without VEP consequence), the code falls back to `info.get('risk_allele')` from the mapping. Since no mapping has this field, the variable is `None`, and the allele comparison `if ann_alt in alleles` is silently skipped — meaning the variant is included without any allele check.

**Fix:** Either:
- (a) Populate `risk_allele` when inserting into `variant_mappings` during ETL / discovery, or
- (b) Skip the variant entirely when both annotation allele and mapping `risk_allele` are absent, instead of proceeding without verification.

---

### 1.3 🔴 zygosity_adjust silently preserves baseline when ref_allele is None

**File:** `backend/services/insight_generators/base.py` — `zygosity_adjust()` ~line 594  
**Impact:** For variants where `ref_allele` is `None`, homozygous non-reference calls (e.g., `A/A` when risk allele is `A`) are treated as baseline risk instead of receiving the expected +1 severity step. The user's risk is systematically underestimated.

```python
if ref_allele is None:
    new_idx = idx  # Silently preserves baseline — no escalation
else:
    new_idx = min(len(_SEVERITY_LADDER) - 1, idx + steps)
```

**Fix:** When `ref_allele` is `None` but a pathogenicity score confirms the variant is pathogenic, apply at least partial escalation (e.g., `+steps // 2`). Or require `ref_allele` to be resolved before building insights.

---

### 1.4 🔴 Multiplier-only fallback inflates risk for variants with no pathogenicity data

**File:** `backend/services/insight_generators/base.py` — `assess_risk_level()` ~line 645  
**Impact:** When no `pathogenicity_score` is available, any variant with `risk_multiplier >= 1.7` is classified as `high` risk — regardless of actual clinical evidence.

```python
# Fallback when pathogenicity unavailable
if risk_multiplier >= 1.7:  base = 'high'
elif risk_multiplier >= 1.2: base = 'moderate'
```

A benign or VUS variant in a gene with a large population risk multiplier (e.g., ApoE locus) will show as "high risk" even though it carries no individual pathogenicity evidence.

**Fix:** When falling back to multiplier-only mode, cap at `moderate` unless ClinVar explicitly classifies the variant as pathogenic. Add this guard:

```python
# In multiplier-only fallback: never go above 'moderate' without pathogenicity data
if risk_multiplier >= 1.7: base = 'moderate'  # downgraded from 'high'
```

---

### 1.5 🔴 Gene-map drug matching skips benign filter

**File:** `backend/services/insight_generators/drug_response.py` — line ~67  
**Impact:** Benign variants in pharmacogenes (e.g., CYP2C9, CYP2D6) can trigger drug response warnings. A user with a confirmed-benign variant in CYP2C9 may be told they are a "poor metabolizer" for warfarin.

The rsid-based path checks `is_clinvar_benign()` before building any insight. The gene-based drug response path does not have an equivalent benign guard.

**Fix:** Add the same benign check used in `generate_from_maps()` to the gene-based drug response loop:

```python
if is_clinvar_benign(annotation_result):
    continue
```

---

## 2. High Priority Bugs

### 2.1 🟠 Silent exception swallowing in mapping enrichment

**File:** `backend/services/analysis_service.py` — ~line 574  

```python
try:
    result = await session.execute(stmt)
    if result.rowcount > 0:
        new_mappings += 1
except Exception:
    pass  # DB errors, serialization failures silently discarded
```

**Impact:** Failed DB writes during `VariantMapping` creation are invisible. The progress counter `new_mappings` will be wrong. Investigation of data gaps is impossible.

**Fix:** Replace `except Exception: pass` with:
```python
except Exception as e:
    logger.warning(f"Failed to upsert variant_mapping for {rsid}: {e}")
```

---

### 2.2 🟠 Analysis resume cannot distinguish interrupted from never-started

**File:** `backend/services/analysis_service.py` — ~line 240  

When `current_step = 'annotating_variants'`, it is impossible to know whether:
- Phase 2 annotation has never been started, or
- Phase 2 was 80% done and the worker crashed

Both situations map to `last_completed_phase = 0`, causing a full restart and re-annotating variants that may already be in `shared_variant_annotations`.

**Fix:** Add a separate status field to track per-phase completion, or set `current_step` to `'annotation_complete'` only after Phase 2 finishes, so an in-progress `'annotating_variants'` always means resume from beginning of Phase 2.

---

### 2.3 🟠 Cognitive generator uses hardcoded flat percentile adjustments

**File:** `backend/services/insight_generators/cognitive.py`  

The cognitive generator applies a hardcoded ±10 percentile adjustment for hom-ref/hom-alt, and no adjustment for heterozygous. This is not zygosity-aware in the way other generators are. A homozygous protective variant gives the same +10% as a heterozygous one will give 0.

**Fix:** Use the standardized `zygosity_adjust()` helper from `base.py` with `step=1`, consistent with all other generators.

---

### 2.4 🟠 boost_if_pathogenic() called before zygosity_adjust() in 6 generators

**Files:** `wellness.py`, `sports.py`, `nutrition.py`, `detox.py`, `methylation.py`, `personality.py`  

These generators call `boost_if_pathogenic()` first and `zygosity_adjust()` second. `health.py` does the reverse via `assess_risk_level()`. The order matters because `boost_if_pathogenic()` may escalate the level that `zygosity_adjust()` then operates on.

A homozygous-reference user with a pathogenic annotation would be:
- In `health.py`: hom-ref `→ de-escalate → apply pathogenicity boost`  
- In the 6 generators above: `boost first → then de-escalate` → net result identical only if de-escalation fully offsets the boost

No bugs in simple cases, but logic is inconsistent and produces different edge-case behavior.

**Fix:** Standardize all generators to call `boost_if_pathogenic()` then `zygosity_adjust()`, or vice versa — but pick one and apply uniformly.

---

## 3. Medium Priority Issues

### 3.1 🟡 annotation_data type not validated before .get()

**File:** `backend/services/analysis_service.py` — ~line 363  

```python
annotated_with_data = sum(1 for ar in annotation_results.values()
    if ar.annotation_data and ar.annotation_data.get('annotations'))
```

If `ar.annotation_data` is a string (e.g., an error message stored by a failed annotation) instead of a dict, `.get()` raises `AttributeError`. This would make the entire annotation stats summary fail.

**Fix:**
```python
if ar.annotation_data and isinstance(ar.annotation_data, dict) and ar.annotation_data.get('annotations')
```

---

### 3.2 🟡 LitVar/PubMed data not surfaced in VariantDetailDialog

**Frontend:** `VariantDetailDialog.tsx`  
`litvar_data` is stored in `shared_variant_annotations` and returned by the annotation API, but the dialog only renders Ensembl, ClinVar, gnomAD, PharmGKB, and AlphaMissense sections. Literature links from LitVar are silently dropped.

**Fix:** Add a "Literature" section to the dialog using `litvar_data.citations` or similar.

---

### 3.3 🟡 Alias mapping for severity levels is incomplete

**File:** `backend/services/insight_generators/base.py` — `_LEVEL_ALIASES` ~line 556  

Auto-categorizer may produce level strings not in the alias map (e.g., `'low_risk'`, `'very low'`, `'normal'`). These fall through to `zygosity_adjust()` which logs a debug warning and returns the unrecognized string unchanged, which is not in the severity ladder.

**Fix:** Either expand `_LEVEL_ALIASES` to cover all auto-categorizer outputs, or add a validation step that normalizes unknown values to `'average'` (baseline) and logs a warning.

---

### 3.4 🟡 N (unknown nucleotide) treated inconsistently

**File:** `backend/services/insight_generators/base.py` — `is_indel_genotype()` ~line 284  

The letter `N` (unknown base) is treated as an indel marker. If a user's genotype contains `N` alleles (which can appear in low-quality SNP array calls), the variant is treated as an indel and skips allele verification.

**Fix:** Explicitly classify `N`-containing genotypes as no-call or skip them before reaching indel/SNP routing.

---

### 3.5 🟡 No timeout on remote API calls

**File:** `backend/services/genetic_api_service.py`  

External API calls to Ensembl REST, ClinPGx, SNPedia, and LitVar have rate-limiting but no hard timeout. A hanging HTTP connection can block an analysis worker indefinitely.

**Fix:** Wrap all external API calls with `asyncio.wait_for(..., timeout=30)` and log timeouts as `source='timeout'` rather than crashing the worker.

---

### 3.6 🟡 rare_mutations ignores composite pathogenicity score for conflicting ClinVar

**File:** `backend/services/insight_generators/rare_mutations.py` — ~line 165  

When ClinVar classification is `'conflicting_interpretations'`, the code stores `mutation_type = 'conflicting_evidence'` and proceeds. The pre-computed composite pathogenicity score (which integrates gnomAD frequency, CADD, AlphaMissense, and ClinVar weight) is not consulted to resolve the conflict.

**Fix:** For conflicting variants, use composite score ≥ 0.60 to promote to `'likely_significant'`, and ≤ 0.30 to downgrade to `'uncertain_significance'`.

---

## 4. Database Schema Issues

### 4.1 🔴 risk_score stored as String, should be Float

**File:** `backend/db/models.py` — `HealthRisk` ~line 208  
**Current:** `risk_score = Column(String)`  
**DB observed values:** `"0.8"`, `"0.6"`, `"0.95"`, `"0.4"`, `"0.2"` (float strings)

This prevents:
- Numeric comparison queries: `WHERE risk_score > 0.5`
- Statistical aggregations: `AVG(risk_score)`
- Proper sorting by risk severity

**Fix:**
1. Create Alembic migration to change column type: `ALTER TABLE health_risks ALTER COLUMN risk_score TYPE FLOAT USING risk_score::float`
2. Update `models.py`: `risk_score = Column(Float, nullable=True)`
3. Ensure all insight generators store float values, not strings

---

### 4.2 🟡 alt_alleles nullable on genetic_markers

**File:** `backend/db/models.py` — `GeneticMarker` ~line 139  
`alt_alleles = Column(String, nullable=True)` — but alt_alleles are required for variant identity. A variant with NULL alt_alleles cannot be correctly deduplicated or annotated.

**Fix:** `alt_alleles = Column(String, nullable=False, default='')`  
Add data migration to set `''` for any existing NULL rows.

---

### 4.3 🟡 genotype nullable on analysis_variants

**File:** `backend/db/models.py` — `AnalysisVariant` ~line 163  
`genotype = Column(String, nullable=True)` — but insight generators skip variants with no genotype. A NULL genotype is functionally equivalent to a missing upload, and insight generation silently produces fewer results with no indication of why.

**Fix:** Default to `'./.'` (VCF no-call convention): `genotype = Column(String, nullable=False, default='./.')`

---

### 4.4 🟡 info column on analysis_variants has no default

**File:** `backend/db/models.py` — `AnalysisVariant` ~line 166  
`info = Column(JSON, nullable=True)` — VCF INFO field dict. Reads of `variant.info.get(...)` will throw `AttributeError` when `info` is NULL.

**Fix:** `info = Column(JSON, nullable=True, server_default='{}')`

---

### 4.5 🟡 SharedVariantAnnotation rows can exceed 5 MB

**File:** `backend/db/models.py` — `SharedVariantAnnotation`  

13 JSON columns store full API responses. A populated row (Ensembl + ClinVar + gnomAD + 1000G + PharmGKB + AlphaMissense + ...) can easily exceed 5 MB. At 714K rows, this is how the table already sits at 4.5 GB.

**Fix options:**
1. **Compression:** Store gzip-compressed bytes and decompress on read (PostgreSQL `bytea` + app-level compression)
2. **Normalization:** Split into `shared_annotation_ensembl`, `shared_annotation_clinvar`, etc. — one row per source per marker
3. **Pruning:** Remove redundant fields from API responses before storing (keep only what generators actually read)

---

### 4.6 🔵 JSON column shapes undocumented

Most JSON columns in insight tables have no schema validation — content shape is inferred by convention only. `annotation_schemas.py` exists but coverage is partial.

**Fix:** Add TypedDicts to `annotation_schemas.py` for every JSON column and validate on insert in service layer. See §5 in `docs/architecture.md` for the full column inventory.

---

## 5. DRY Violations

### 5.1 Strand-flip complement map defined in 3 places

- `base.py` — `generate_from_maps()` inline
- `rare_mutations.py` — line ~37
- `uncommon_mutations.py` — line ~25

**Fix:** Define `_ALLELE_COMPLEMENT = str.maketrans('ACGT', 'TGCA')` once in `base.py` and import it in all generators.

---

### 5.2 Consequence severity filter duplicated

- `uncommon_mutations.py` — lines ~29-37: list of functional consequence types
- `generate_from_maps()` in `base.py` — lines ~858-877: same list maintained separately

Both need to stay in sync when new consequence types emerge from Ensembl VEP.

**Fix:** Create `is_functional_consequence(consequence: str) -> bool` in `base.py` and import it in `uncommon_mutations.py`.

---

### 5.3 ClinVar significance keyword matching duplicated

The pattern `if 'pathogenic' in clinical_significance` (and variants with `likely_pathogenic`, `risk_factor`, etc.) appears in at least 4 files:
- `health.py`, `carrier.py`, `rare_mutations.py`, `drug_response.py`

**Fix:** Create `extract_clinical_significance(annotation_result)` returning a normalized enum, used everywhere.

---

### 5.4 Population frequency extraction duplicated

Both `ancestry.py` and `rare_mutations.py` independently parse gnomAD / 1000G frequency data from annotation dicts.

**Fix:** Add `extract_population_frequency(annotation_result, population: str = 'global') -> Optional[float]` to `base.py`.

---

### 5.5 Benign filtering condition duplicated before generator dispatch

`is_clinvar_benign()` is called:
- Once in `generate_from_maps()` rsid path (all generators using generic method)
- Again in `generate_from_maps()` gene path
- Separately in `rare_mutations.py` with a different criterion
- Potentially in `drug_response.py` (rsid path only)

**Fix:** Filter benign variants in `insight_dispatcher.py` before any generator sees them, as a pre-processing step on the `VariantProfile` list. Set `profile.is_benign = True` and have generators check this flag rather than re-inspecting ClinVar data.

---

## 6. Separation of Concerns

### 6.1 Zygosity classification has two divergent implementations

- `base.py` — `is_homozygous_reference()` uses allele-length comparison for D/I codes
- `carrier.py` — `_classify_carrier_status()` reimplements indel zygosity with different logic

These may generate different is-hom-ref results for the same variant depending on which generator runs.

**Fix:** Consolidate all zygosity logic into `base.py::classify_zygosity()` returning `'hom_ref' | 'het' | 'hom_alt' | 'no_call'`. Use it everywhere.

---

### 6.2 Gene extraction tries 4 sources inside generator

`extract_gene_and_consequence()` in `base.py` chains through: Ensembl → ClinVar-local → gnomAD → ClinVar DB. This data source priority logic mixed with business logic makes the function hard to test and change.

**Fix:** Move multi-source gene extraction into `VariantProfile` construction at the `insight_dispatcher.py` level (it runs once before all generators). Generators should only read `profile.gene`.

---

### 6.3 Pathogenicity scoring fetched in two places

The composite pathogenicity score is:
1. Pre-computed in `insight_dispatcher.py` and stored in `VariantProfile.composite_score`
2. Also fetched from annotation_data inside some generators as a fallback

**Fix:** Remove the per-generator fallback. Require generators to only read from `profile.composite_score`. If score is unavailable at dispatch time, that's a `VariantProfile` construction bug to fix there.

---

## 7. Architecture Concerns

### 7.1 Services not registered in DI container after refactor

After splitting `ComprehensiveAnalysisService` into smaller modules (`variant_loader.py`, `annotation_coordinator.py`, `insight_dispatcher.py`), these were not registered in `container.py`. They are instantiated inline in `analysis_service.py`.

**Impact:** Testing these services in isolation requires mocking their creation call sites, not the container.

**Fix:** Register as singletons:
```python
container.register_singleton('variant_loader', VariantLoader)
container.register_singleton('annotation_coordinator', AnnotationCoordinator)
container.register_singleton('insight_dispatcher', InsightDispatcher)
```

---

### 7.2 Copilot instructions reference deleted table

`.github/copilot-instructions.md` mentions `panel_marker_configs` as a current config table. This table was dropped in migration `014_drop_panel_marker_configs.py`. The equivalent is now `variant_mappings`.

**Fix:** Update the instructions file to remove the `panel_marker_configs` reference and document `variant_mappings` correctly.

---

### 7.3 API service transient re-initialization is expensive

`OptimizedGeneticAPIService` is registered as `transient` in `container.py`, meaning a new instance is created for every consumer. This service initializes HTTP clients and rate limiters on creation.

**Fix:** Register as `request_scoped` tied to the analysis job lifecycle, or as a singleton if thread-safety is confirmed.

---

### 7.4 Panel markers have no allele specificity

`variant_mappings` stores mappings keyed by rsid alone (`map_type='rsid'`, `key='rs7903146'`). The specific pathogenic allele is not stored (and DB confirms: 0 rows have `risk_allele` populated).

**Impact:** Two users with the same rsid but different alleles (one carrying the risk allele `T`, one carrying only `G`) get the same mapping lookup, and allele discrimination relies entirely on the annotation API returning the correct alt allele. If annotation is unavailable, both are treated the same.

**Fix:** Add optional `allele` column to `variant_mappings`:
```sql
ALTER TABLE variant_mappings ADD COLUMN allele VARCHAR;
```
Populate during ETL/discovery from ClinVar `ClinicalAllele` data. Filter in generator: skip if `profile.risk_allele != mapping.allele`.

---

## 8. Frontend Issues

### 8.1 GeneticAnnotation.tsx is exported but never imported

**File:** `frontend/src/components/GeneticAnnotation.tsx`  
This component is defined and exported but does not appear in any `import` statement in the codebase. It renders a standalone annotation viewer that duplicates functionality already in `VariantDetailDialog.tsx`.

**Action:** Either integrate into an appropriate panel or delete to reduce bundle size.

---

### 8.2 LitVar literature data not rendered

**File:** `frontend/src/components/categories/VariantDetailDialog.tsx`  
`litvar_data` is returned by `/api/annotations/variant/{rsid}` but the dialog has no section to render it. PubMed citations exist in the DB but are inaccessible in the UI.

---

### 8.3 Risk score rendered as string badge, not numeric

**File:** All panel components using `risk_score`  
Since `risk_score` is stored and returned as a string (`"0.8"`, not `0.8`), frontend panels cannot sort by risk or compute averages without explicit `parseFloat()` calls. Currently rendered as pure text badges.

After fixing issue 4.1 (schema), ensure API serialization uses `float` type.

---

## 9. Dead / Unused Code

### 9.1 get_health_recommendations() — effectively inert

**File:** `backend/services/insight_generators/base.py` — `get_health_recommendations()` ~line 647  

Only handles `'Type 2 Diabetes'` and `'Cardiovascular Disease'` specifically. Every other condition gets `"Consult with healthcare provider"`. The function is called in the health generator but provides no differentiated value for 99% of conditions.

**Action:** Either expand with meaningful per-condition recommendations or remove and consolidate into the mapping `data['recommendations']` field.

---

### 9.2 get_trait_description() — single template string

**File:** `backend/services/insight_generators/base.py` — `get_trait_description()` ~line 662  

Returns: `f"Genetic analysis indicates {result} for {trait}"` for every trait. Not referenced from templates or user-visible text — physical_traits generator calls it but the result is the same generic string every time.

**Action:** Remove this function. Inline the format string at the one call site, or use the mapping's `data['description']` field.

---

### 9.3 drug_response etl files — no evidence of use

**Files:** `backend/services/drug_response.py` (if it exists separately from `insight_generators/drug_response.py`)  

Check if `services/drug_response.py` is distinct from `services/insight_generators/drug_response.py` and whether it's imported anywhere.

---

### 9.4 clinvar_etl.py, ensembl_etl.py, gnomad_etl.py, ensembl_vep_etl.py, thousand_genomes_etl.py

These ETL files are used during data import (admin ETL pipeline) but are not called during normal analysis. They are correctly scoped to import operations only. No action needed but worth confirming they're only triggered by admin API routes.

---

## 10. Data Observations

### Live DB State (as of audit)

| Metric | Value |
|--------|-------|
| Users | 2 |
| Completed analyses | 2 |
| Total genetic markers | 731,703 |
| Annotated variants (ensembl_data) | 714,586 |
| Variant mappings total | ~237,000 |
| `risk_allele` populated in mappings | **0** (confirms BUG 1.2 is active) |
| Health risks stored | 1,057 |
| Uncommon mutations mappings | 224,115 (93% of non-health mappings) |

### Risk Score Distribution in health_risks

```
risk_level   | risk_score | count
very_high    | 0.95       |   262
high         | 0.8        |   424
moderate     | 0.6        |   328
average      | 0.4        |    35
low          | 0.2        |     8
```

The distribution skews heavily toward `high` and `very_high`. Combined with the allele verification gaps (§1.1, §1.2), this suggests many of these 686 high/very-high results may not actually reflect the user's genotype accurately.

### Table Size Concerns

| Table | Size | Note |
|-------|------|------|
| `thousand_genomes_variants` | 16 GB | Expected — 1000G Phase 3 full dataset |
| `shared_variant_annotations` | 4.5 GB | Growing indefinitely (see §4.5) |
| `clinvar_variants` | 2.6 GB | Expected — full ClinVar VCF |
| `analysis_variants` | 367 MB | Large for 731K markers; check index coverage |
| `variant_mappings` | 126 MB | 237K rows with JSON — index on (category, map_type, key) critical |

---

## Priority Fix Order

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 1 | §1.1 — Indel allele verification bypass | Medium | Eliminates false positives for all indel rsids |
| 2 | §1.2 — risk_allele missing from mappings | Low (ETL addition) | Enables allele fallback verification |
| 3 | §4.1 — risk_score as Float | Low (migration) | Enables numeric filtering and sorting |
| 4 | §1.3 — zygosity_adjust with None ref | Low | Corrects risk underestimation in hom-alt |
| 5 | §1.5 — drug_response gene-map benign bypass | Low | Eliminates false drug warnings |
| 6 | §2.1 — Silent exception in mapping enrichment | Trivial | Restores observability |
| 7 | §1.4 — Multiplier-only risk inflation | Low | Reduces false high-risk flags |
| 8 | §5.1–5.5 — DRY violations | Medium | Reduces maintenance surface |
| 9 | §4.5 — SharedVariantAnnotation bloat strategy | High | Long-term storage scalability |
| 10 | §7.4 — Add allele column to variant_mappings | High effort | Foundational correctness improvement |
