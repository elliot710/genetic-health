# Genetic Health Analysis Toolkit — Architecture Documentation

> **Last updated:** March 18, 2026  
> **Codebase:** ~68K LOC backend (Python), ~12K LOC frontend (TypeScript/React)  
> **Database:** PostgreSQL 15, ~714K shared annotations, ~21M+ local data rows  

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Infrastructure & Deployment](#2-infrastructure--deployment)
3. [Backend Architecture](#3-backend-architecture)
4. [Analysis Pipeline (4 Phases)](#4-analysis-pipeline-4-phases)
5. [Variant Registry & Panel Markers](#5-variant-registry--panel-markers)
6. [Scoring Engine](#6-scoring-engine)
7. [Insight Generators](#7-insight-generators)
8. [Database Architecture](#8-database-architecture)
9. [Annotation Data Coverage (Actual State)](#9-annotation-data-coverage-actual-state)
10. [Frontend Architecture](#10-frontend-architecture)
11. [Security Model](#11-security-model)

---

## 1. System Overview

The toolkit ingests consumer genetics CSV/VCF files (23andMe, AncestryDNA) containing ~600K–700K SNPs and produces personalized health insights across 13 categories. The pipeline is structured as a 4-phase background job with an annotation deduplication cache to avoid re-querying external APIs for variants already seen.

### 13 Insight Categories

| Category | Table | Generator | Insight count (typical) |
|----------|-------|-----------|------------------------|
| Health Risks | `health_risks` | `health.py` | 2–20 |
| Drug Responses | `drug_responses` | `drug_response.py` | 20–80 |
| Physical Traits | `physical_traits` | `physical_traits.py` | 2–10 |
| Nutrition | `nutrition_traits` | `nutrition.py` | 3–12 |
| Sports Performance | `sports_performance` | `sports.py` | 5–15 |
| Cognitive Profiles | `cognitive_profiles` | `cognitive.py` | 2–8 |
| Personality Traits | `personality_traits` | `personality.py` | 2–8 |
| Ancestry | `ancestry_results` | `ancestry.py` | 1 (aggregate) |
| Carrier Status | `carrier_status` | `carrier.py` | 100–600 |
| Wellness Metrics | `wellness_metrics` | `wellness.py` | 5–20 |
| Methylation | `methylation_profiles` | `methylation.py` | 1–10 |
| Detoxification | `detoxification_profiles` | `detox.py` | 2–8 |
| Rare Mutations | `rare_mutations` | `rare_mutations.py` | 50–2000 |
| Uncommon Mutations | `uncommon_mutations` | `uncommon_mutations.py` | 0 (broken — see improvements) |

---

## 2. Infrastructure & Deployment

### Docker Compose

Three containers:

| Service | Image | Port | Health Check |
|---------|-------|------|-------------|
| `postgres` | `postgres:15` | 5432 | `pg_isready` every 10s |
| `backend` | Python 3.11-slim + UV | 8000 | `curl /health` every 30s |
| `frontend` | Node.js + pnpm | 3000 | None |

Startup order: postgres → backend → frontend. Backend hot-reloads via `uvicorn --reload`. Frontend uses Turbopack.

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | Yes | asyncpg connection string |
| `SECRET_KEY` | Yes | JWT HS256 signing (app raises `RuntimeError` if unset) |
| `NCBI_API_KEY` | Recommended | NCBI rate limit 3→10 req/s |
| `ALPHA_MISSENSE_DATA_DIR` | Optional | Tabix-indexed AM TSV files |
| `CLINVAR_DATA_DIR` | Optional | ClinVar TSV/VCF for ETL |
| `GNOMAD_DATA_DIR` | Optional | gnomAD CADD TSV for ETL |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional | BigQuery (ChEMBL/FDA/AlphaFold) |

---

## 3. Backend Architecture

### Application Structure

```
backend/
├── main.py                    # FastAPI app, CORS, 7 router mounts, startup/shutdown
├── worker.py                  # Celery-like background worker (picks jobs from DB)
├── api/                       # 7 route handlers
│   ├── auth_routes.py         # /auth — register, login, me, change-password
│   ├── upload_routes.py       # /upload — VCF/CSV upload, delete data
│   ├── analysis_routes.py     # /api/analysis — start, status, SSE stream, dashboard-data
│   ├── annotation_routes.py   # /api/annotations — variant details, literature, summary
│   ├── variant_routes.py      # /api/variants — cached multi-source lookup
│   ├── admin_routes.py        # /api/admin — users, panels, markers, discoveries, rules
│   └── insights_routes.py     # /api/insights — LLM insights (experimental)
├── services/
│   ├── analysis_service.py    # ComprehensiveAnalysisService — main orchestrator (~2700 LOC)
│   ├── shared_annotation_service.py  # Annotation cache reads/writes
│   ├── scoring_engine.py      # ScoringEngine — 9-source composite pathogenicity score
│   ├── auto_categorizer.py    # AutoCategorizer — generates VariantMapping from ClinVar rules
│   ├── insight_generators/    # 14 category-specific generators
│   ├── genetic_api_service.py # Remote API calls (Ensembl, ClinVar, ClinPGx, SNPedia, LitVar)
│   ├── clinvar_local.py       # ClinVar PostgreSQL queries
│   ├── gnomad_local.py        # gnomAD PostgreSQL queries
│   ├── ensembl_local.py       # Ensembl gene table (position-based gene lookup)
│   ├── ensembl_vep_local.py   # Pre-computed VEP consequences table
│   ├── gnomad_tx.py           # gnomAD transcript annotations (tabix)
│   ├── thousand_genomes_local.py  # 1000 Genomes superpopulation frequencies
│   └── job_logs.py            # Per-job log collection via contextvars
├── db/
│   ├── models.py              # All SQLAlchemy ORM models (~860 LOC)
│   ├── database.py            # Async engine, session factory
│   └── schemas.py             # Pydantic request/response schemas
└── core/
    ├── auth.py                # JWT HS256, 10-day expiry, bcrypt
    ├── config.py              # Settings (env vars)
    ├── container.py           # DI container (singletons, factories, transients)
    └── exceptions.py          # Custom exception hierarchy
```

### Job Queue Architecture

The analysis system uses a custom lightweight job queue rather than Celery:

- `analysis_queue.py`: `AnalysisQueue` singleton, `asyncio.Queue`, max 3 global concurrent jobs, max 2 per user
- `worker.py`: Separate process polling for `pending` jobs in the DB, dispatches to `ComprehensiveAnalysisService`
- On server restart: stale `processing` jobs are automatically re-queued
- User controls: pause, resume, cancel (via DB status update + `AnalysisCancelled` exception check)

### Dependency Injection

`core/container.py` provides a lightweight DI container:
- **Singleton**: created once, shared (e.g. `HealthInsights`, `DrugResponseAnalyzer`)
- **Factory**: created once on first use, then cached
- **Transient**: new instance per `get()` call (e.g. `OptimizedGeneticAPIService`, to avoid cross-user cache contamination)

---

## 4. Analysis Pipeline (4 Phases)

### Phase 1: Gene Map (0–2%, seconds)

Builds an `rsid → gene_symbol` lookup dictionary used throughout Phase 4.

Two sources queried in sequence:
1. **ClinVar DB** — `SELECT rsid, gene FROM clinvar_variants WHERE rsid IN (...)` in 1K-row batches. Covers ~6% of typical user variants (~37K of 614K in job logs). `DISTINCT ON(rsid)` — non-deterministic gene for multi-gene rsids.
2. **Ensembl local** — `batch_position_to_gene(chr, pos)` from the `ensembl_genes` table (60K gene models with start/end coordinates). Covers ~54% of remaining variants via genomic interval overlap. Total typical coverage: **60.5%** of all user RSIDs.

### Phase 2: Annotation (2–30%, minutes)

Annotates all variants with multi-source data, maximizing cache reuse.

**Cache check** (`SharedVariantAnnotationService.get_existing_annotations`):
- Queries `shared_variant_annotations` in 500-row batches
- Merges all source columns into `annotation_data['annotations']` dict
- Calls `ScoringEngine.score_variant()` to compute `pathogenicity_score` for each cached annotation
- Increments `usage_count` for found annotations (30K rows per batch update)

**For new RSIDs** (not in cache):
- Calls remote APIs (Ensembl VEP REST, ClinVar NCBI, ClinPGx, SNPedia, LitVar)
- Calls local sources (AlphaMissense tabix, ClinVar PG, gnomAD PG, 1000G PG)
- Upserts into `shared_variant_annotations`

**Local source backfill** (for cached annotations missing specific sources):
- If `alpha_missense_data` is NULL or stale: batch tabix lookup
- If `gnomad_tx_data` is NULL or stale: batch tabix lookup
- Other local sources (clinvar_local, ensembl, 1000g) are backfilled only for genuinely new variants

**Phase 2.5: ref_allele correction**  
Consumer CSV files set `ref_allele = genotype[0]` — often wrong. After annotation, authoritative ref alleles from gnomAD/Ensembl/ClinVar/1000G are written back to `genetic_markers.ref_allele`. This is critical for correct zygosity classification in Phase 4.

### Phase 3: BigQuery Enrichment (30–90%)

Optional enrichment from Google BigQuery public datasets:
- `gnomad_bigquery.py`: gnomAD variant frequencies, gene constraints
- `bq_public.py`: ChEMBL drug mechanisms, FDA drug labels, AlphaFold confidence

Currently **disabled** in the deployment (BigQuery sources not enabled). Phase 3 always completes in 0.0s.

### Phase 4: Insight Generation (90–100%, 2–3 minutes)

```python
# In analysis_service._generate_comprehensive_insights():
profiles = await build_variant_profiles(variants, annotation_results, rsid_gene_map)
ctx = GeneratorContext(analysis_id, variants, annotation_results, session, rsid_gene_map, registry, profiles)
for name, generator_fn in ALL_GENERATORS:
    count = await generator_fn(ctx)
```

1. **`build_variant_profiles()`** — single pass over all variants, pre-computes per-rsid: genotype, effective_ref, gene, consequence, impact, population_frequency, clinical_significance, zygosity flags, composite_score. ~17 seconds for 614K variants.
2. **14 generator functions** — each reads from `ctx` (profiles, registry, annotation_results) and writes rows to their insight table.

---

## 5. Variant Registry & Panel Markers

### Two Separate Systems (NOT interconnected)

The codebase has two independent marker/mapping tables that serve different purposes:

#### 5.1 `variant_mappings` — Used by insight generators

The **active registry** that all 14 insight generators read at analysis time.

```
variant_mappings:
  category      VARCHAR   -- health, drug, carrier, methylation, detox, ...
  map_type      VARCHAR   -- 'rsid' or 'gene'
  key           VARCHAR   -- the rsid or gene symbol
  data          JSON      -- category-specific payload
  is_active     BOOLEAN
  is_auto_discovered  BOOLEAN
```

Loaded once per analysis via `ComprehensiveAnalysisService._load_registry()` into an in-memory dict:
```python
registry[category]['rsid'][rsid] = data_dict
registry[category]['gene'][gene_symbol] = data_dict
```

**Current state (March 2026):**
- 20,105 active mappings across 12 categories
- ~90% auto-discovered (generated by `AutoCategorizer`)
- ~10% manually seeded with curated data

Category breakdown:
| Category | rsid mappings | gene mappings | Notes |
|----------|---------------|---------------|-------|
| carrier | 2,010 | 0 | All rsid |
| health | 2,005 | 18 | 5 manually seeded rsids |
| cognitive | 2,003 | 23 | |
| methylation | 2,200 | 21 | 5 manually seeded rsids |
| nutrition | 2,202 | 26 | |
| personality | 2,280 | 20 | |
| physical | 2,005 | 26 | |
| sports | 2,283 | 27 | |
| wellness | 2,363 | 24 | |
| drug | 132 | 37 | 20 manually seeded gene entries |
| detox | 363 | 27 | |
| ancestry | 0 | 10 | |

**Data quality issues in auto-discovered mappings:**
- `health`: 266 entries with garbage conditions ('not provided', 'not specified', 'Inborn genetic diseases')
- All non-health categories: `risk_multiplier` field absent (not needed by their generators)
- `carrier`: 2,000 entries — condition may include generic ClinVar labels

#### 5.2 `panel_marker_configs` — NOT used by insight generators

An admin-managed table that defines which specific rsids belong to each dashboard panel. **This table is not read by any insight generator.** It is only used by `DiscoveryService` to check whether newly discovered markers are already configured.

```
panel_marker_configs:
  panel_id      VARCHAR   -- 'health', 'rare_mutations', 'methylation', ...
  rsid          VARCHAR
  gene          VARCHAR
  description   VARCHAR
  category      VARCHAR   -- sub-category within panel
```

Current state: 20,221 active panel markers across 14 panels, including carefully curated entries like:
- BRCA1/BRCA2/TP53 in `rare_mutations`
- APOE/PPARG/FTO in `health`
- CYP2D6/CYP2C19/VKORC1 in `drug_responses`

**None of these feed into the insight generators.** The `rare_mutations` panel has 10 curated entries (BRCA1, BRCA2, TP53, etc.) that would generate high-value clinical insights — but because `panel_marker_configs` is disconnected from `variant_mappings`, the `rare_mutations` generator never uses them. The generator instead works entirely from ClinVar local data.

#### 5.3 AutoCategorizer — Generates variant_mappings

`services/auto_categorizer.py` reads from `category_rules` table and generates `VariantMapping` rows by running 7 rule types against ClinVar and gnomAD:

| Rule Type | Logic | Max per category |
|-----------|-------|-----------------|
| `clinvar_significance` | Match by clinical significance (Pathogenic, Likely_pathogenic) | 2000 |
| `clinvar_condition_keyword` | Match by ClinVar conditions containing keyword | 2000 |
| `gene_list` | Match genes in comma-separated list → gene-type mappings | unlimited |
| `molecular_consequence` | Match VEP consequence type | 2000 |
| `origin` | Match germline/somatic origin | 2000 |
| `gnomad_rare_variant` | Match by AF < threshold | 2000 |
| `gnomad_constrained_gene` | Match by pLI/LOEUF constraint | 2000 |

Risk multiplier assignment in condition_keyword matches:
- `pathogenic` in significance → `risk_multiplier = max(existing, 2.5)` (set to 3.0 for template rules)
- `likely` in significance → multiplier kept at template value
- `uncertain`/`conflicting` → `risk_multiplier = min(existing, 1.3)`
- `risk_factor` → multiplier at 1.5

---

## 6. Scoring Engine

`services/scoring_engine.py` — Aggregates up to 9 evidence sources into a composite pathogenicity score (0–1).

### Source Weights

| Source | Weight | From |
|--------|--------|------|
| ClinVar (API) | 0.30 | `ensembl_data` / remote API |
| ClinVar Local | 0.30 | `clinvar_local_data` / PostgreSQL |
| CADD PHRED | 0.15 | `gnomad_data.cadd.phred` |
| AlphaMissense | 0.15 | `alpha_missense_data.score` |
| gnomAD AF | 0.10 | `gnomad_data.af` |
| SIFT | 0.05 | `gnomad_data.predictions.sift` |
| PolyPhen | 0.05 | `gnomad_data.predictions.polyphen` |
| PhyloP Conservation | 0.05 | `gnomad_data.conservation.vertebrate` |
| SpliceAI | 0.05 | `gnomad_data.splice_ai.max_score` |

**Note**: CADD, SIFT, PolyPhen, PhyloP, SpliceAI, and gnomAD AF are almost never populated (only 305/714K annotations have gnomAD data). In practice the scoring engine runs on ClinVar local + AlphaMissense only.

### Deduplication Logic

When both `clinvar` (API) and `clinvar_local` are present, the engine drops `clinvar_local` and uses only the API version. **In the current deployment, all remote API calls are disabled**, so `clinvar_data` is never populated — meaning this dedup logic never actually fires.

### Classification Thresholds

| Composite Score | Classification |
|-----------------|----------------|
| ≥ 0.80 | pathogenic |
| ≥ 0.60 | likely_pathogenic |
| ≥ 0.30 | uncertain |
| ≥ 0.15 | likely_benign |
| < 0.15 | benign |

### Minimum Weight Floor

The denominator is clamped to at least `MIN_WEIGHT_FLOOR = 0.40`. This prevents single low-weight sources from generating inflated scores, but also caps maximum single-source output: a pathogenic ClinVar-only variant (weight=0.30, score=0.95) yields composite = 0.95×0.30 / 0.40 = **0.71** → `likely_pathogenic`, not `pathogenic`.

---

## 7. Insight Generators

All generators live in `services/insight_generators/` and follow the signature:
```python
async def generate_<category>(ctx: GeneratorContext) -> int
```

### Generator Context

```python
@dataclass
class GeneratorContext:
    analysis_id: int
    variants: List[VariantLite]           # All 614K user variants
    annotation_results: Dict[str, AnnotationResult]  # rsid → cached annotation
    session: AsyncSession                  # For writing insight rows
    rsid_gene_map: Dict[str, str]         # From Phase 1
    registry: Dict[str, Dict[str, Dict]]  # From variant_mappings DB
    variant_profiles: Dict[str, VariantProfile]  # Pre-computed zygosity/sig data
```

### Variant Profiles (Pre-computed)

`build_variant_profiles()` runs once before all generators (~17s for 614K variants). Each profile stores:
- `genotype`, `effective_ref` — from variant + annotation cross-reference
- `gene`, `consequence`, `impact` — from Ensembl VEP → fallback to ClinVar → fallback to rsid_gene_map
- `population_frequency` — from Ensembl colocated_variants → gnomAD AF → 1000G
- `clinical_significance` — first significant from ClinVar local
- `is_hom_ref`, `is_het`, `is_no_call` — pre-computed zygosity flags
- `composite_score` — from scoring engine
- `is_benign` — `is_clinvar_benign()` result

### Generic Map-Driven Generator (`generate_from_maps`)

10 of 14 generators (health, physical, nutrition, sports, cognitive, personality, wellness, methylation, detox, drug) use this shared loop:

```
For each variant:
  1. Skip if no_call genotype
  2. Skip if effective_ref available AND is_homozygous_reference
  3. rsid-match: if rsid in registry[category]['rsid']:
     - Skip if is_clinvar_benign()
     - Generate insight if dedup_key not seen
  4. gene-match: if gene in registry[category]['gene']:
     - Require impact in (HIGH, MODERATE) OR functional consequence OR ClinVar path flag
     - Generate insight if dedup_key not seen
```

**Deduplication keys per category:**

| Category | dedup_field | Practical effect |
|----------|-------------|-----------------|
| health | condition | 1 insight per condition name |
| drug | (separate loop) | 1 drug per gene+drug pair |
| physical | trait | 1 insight per trait name |
| nutrition | nutrient | 1 insight per nutrient |
| sports | category | 1 insight per performance category |
| cognitive | domain | 1 insight per cognitive domain |
| personality | trait | 1 insight per trait name |
| wellness | metric | 1 insight per metric name |
| methylation | gene | 1 insight per gene |
| detox | gene | 1 insight per gene |

### Zygosity Adjustment

`zygosity_adjust(level, genotype, ref_allele)` shifts severity on the ladder `[low, average, moderate, high, very_high]`:
- Homozygous ref → de-escalate by 1 step
- Heterozygous → no change (baseline)
- Homozygous alt → escalate by 1 step
- No-call → no change (preserve baseline)

`_LEVEL_ALIASES` maps non-standard values to ladder equivalents:
```python
{'variable': 'average', 'reduced': 'moderate', 'elevated': 'high',
 'elevated risk': 'high', 'elevated_risk': 'high', 'normal': 'average'}
```

**Note**: Several values from manually seeded mappings (`mildly_reduced`, `b12_dependent`, `slow_processing`, `variant_detected`, `sensitive`) are NOT in the alias map and fall through `zygosity_adjust` unchanged.

### Carrier Status Generator

Operates differently from the map-driven generators:
1. Checks registry['carrier']['rsid'] map
2. Independently scans ClinVar local data for all variants with pathogenic significance + gene_conditions
3. Classifies status via `_classify_carrier_status(user_gt, ref_allele, alt_allele)`: `unaffected`, `carrier`, or `affected`
4. Uses `dedup_field=condition` — one entry per unique disease name
5. Generates 100–600 entries for a typical user (many ClinVar-catalogued variants are in genes associated with recessive diseases)

### Rare Mutations Generator

Also operates independently from variant_mappings:
1. Requires ClinVar data (local or API)
2. Requires frequency < 1% (or unknown)
3. Skips homozygous reference and no-call genotypes
4. Classifies significance from ClinVar local `clinical_significances` array
5. Upgrades uncertain/conflicting to `likely_pathogenic` if composite_score ≥ 0.60
6. Skips benign/likely_benign
7. Sorts by clinical priority

Generates 50–2000 entries. A value of 1143 (from the job logs) is within normal range.

### Ancestry Generator

Uses a log-likelihood model over a pre-computed Ancestry-Informative Markers (AIMs) panel:
- Loaded from `ancestry_aims_panel` table (fst_delta ≥ 0.70 = ~60K variants)
- Fetches user variants overlapping the panel via SQL
- Classifies each genotype as hom_ref / het / hom_alt relative to each population's allele frequency
- Sums log-likelihoods per population (AFR, AMR, EAS, EUR, SAS)
- Converts to proportional percentages via softmax-like normalization
- Outputs a single `AncestryResult` row with composition JSON

---

## 8. Database Architecture

### Core Tables

```
users ──1:N── genetic_analyses ──1:N── analysis_variants ──N:1── genetic_markers
                                             │                          │
                                             └── variant_annotations    └── shared_variant_annotations
                                                                              (NEVER DELETED — global cache)
```

**genetic_markers** — global catalog of every uploaded variant by rsid. `upload_count` tracks reuse. Never deleted.

**shared_variant_annotations** — caches all annotation API responses by variant. Never deleted. 13 JSON columns (ensembl_data, clinvar_data, pharmgkb_data, alpha_missense_data, clinvar_local_data, gnomad_data, gnomad_tx_data, thousand_genomes_data, chembl_data, fda_drug_data, alphafold_data). `usage_count` tracks how many analyses reference each.

**analysis_variants** — links one analysis to one global marker with user-specific genotype. CASCADE-deleted.

### Local Data Source Tables (ETL-imported)

| Table | Rows | Source | Query path |
|-------|------|--------|-----------|
| `clinvar_variants` | ~2.5M | ClinVar TSV+VCF | rsid → significances, conditions, genes |
| `clinvar_gene_conditions` | ~30K | ClinVar gene_condition | gene → diseases |
| `gnomad_variants` | ~1M | gnomAD CADD TSV | rsid/(chr,pos,ref,alt) → AF, CADD, SIFT, PolyPhen |
| `gnomad_gene_constraints` | ~20K | gnomAD constraint | gene → pLI, LOEUF |
| `ensembl_genes` | ~60K | Ensembl FASTA headers | (chr, pos) → gene_symbol |
| `ensembl_vep_variants` | ~50K | VEP VCF dump | rsid → consequence |
| `thousand_genomes_variants` | ~80M | 1000G Phase 3 VCF | rsid → superpopulation AFs |
| `ancestry_aims_panel` | ~1.4M | Custom (from 1000G) | rsid → (af_afr, af_amr, af_eas, af_eur, af_sas) |

### Admin/Config Tables

| Table | Purpose |
|-------|---------|
| `variant_mappings` | Registry read by insight generators |
| `panel_marker_configs` | Admin UI panel configuration (NOT used by generators) |
| `category_rules` | AutoCategorizer rules |
| `annotation_source_configs` | Enable/disable annotation sources |
| `pending_discoveries` | Auto-discovered markers pending admin review |
| `variant_lookup_cache` | External API response cache with usage counting |
| `dashboard_cache` | Fingerprint-based dashboard response cache |

### Migrations

10 Alembic revisions:
- 001–006: baseline schema + indexes
- 007: gnomad_tx support
- 008: annotation_source_configs source_type column
- 009: reset broken AlphaMissense/gnomAD-tx annotations
- 010: ancestry_aims_panel table creation

---

## 9. Annotation Data Coverage (Actual State)

Measured from the production database (March 2026, 714,586 annotations):

| Source | Present | Found/Active | Coverage |
|--------|---------|-------------|---------|
| `ensembl_data` | 714,586 (100%) | 712,731 `found:true` | 99.7% |
| `ensembl_data` with `gene_symbol` | — | 1,532 | 0.2% |
| `clinvar_local_data` | 714,586 (100%) | 48,621 `found:true` | 6.8% |
| `alpha_missense_data` | 714,586 (100%) | 2,504 `found:true` | 0.35% |
| `gnomad_data` | 305 | — | 0.04% |
| `thousand_genomes_data` | 714,586 (100%) | — | varies |
| `gnomad_tx_data` | 714,586 (100%) | ~294 positive | ~0.04% |

**Key implications:**
- Gene resolution: 99.7% via Ensembl VEP (consequence+impact, but without gene_symbol in 99.8% of cases) + ClinVar DB rsid→gene map (Phase 1)
- Pathogenicity scoring: primarily ClinVar local (6.8% coverage) + AlphaMissense (0.35%). CADD/SIFT/PolyPhen/AF are effectively absent.
- Population frequency: nearly absent from gnomAD (0.04%). Ensembl `colocated_variants.frequencies` provides coverage for some common variants.

**annotation_status field:**
- 711,792 / 714,586 (99.6%) are `partial` — this is the expected state since gnomAD and remote APIs are disabled. The system still processes partial annotations correctly.
- Only 2,794 are `completed`.

---

## 10. Frontend Architecture

### Technology Stack

| Technology | Purpose |
|-----------|---------|
| Next.js 15 (App Router) | Framework |
| React 19 | UI |
| TypeScript 5 | Type safety |
| Tailwind CSS 4 | Styling |
| shadcn/ui (17 components) | UI primitives (Radix) |
| Recharts 2.x | Charts (11 types) |
| Framer Motion | Animations |
| Lucide React + Tabler Icons | Icons |
| react-simple-maps | World map (ancestry) |
| react-dropzone | File upload |

### Application Flow

```
AuthForm → FileUpload → AnalysisProgressLoader (SSE polling) → Dashboard
```

No client-side routing — hash-based navigation within `app/page.tsx`.

### Component Hierarchy

```
app/page.tsx (SPA orchestrator)
├── AuthForm.tsx
├── FileUpload.tsx
├── AnalysisProgressLoader.tsx (polls /api/analysis/status/{id})
└── Dashboard.tsx (~1900 LOC)
    ├── dashboard/DashboardHeader.tsx
    ├── dashboard/DashboardSidebar.tsx
    ├── dashboard/DashboardOverview.tsx
    ├── 13 Category Panels (lazy-loaded)
    │   ├── HealthPanel.tsx
    │   ├── DrugResponsesPanel.tsx
    │   ├── AncestryPanel.tsx
    │   ├── CarrierStatusPanel.tsx
    │   ├── WellnessPanel.tsx
    │   ├── MethylationPanel.tsx
    │   ├── DetoxPanel.tsx
    │   ├── RareMutationsPanel.tsx
    │   ├── UncommonMutationsPanel.tsx
    │   ├── PhysicalTraitsPanel.tsx
    │   ├── SportsPanel.tsx
    │   ├── FoodNutritionPanel.tsx
    │   └── IntelligencePanel.tsx (= cognitive)
    │   └── PersonalityPanel.tsx
    ├── GenomicCharts.tsx (11 chart types)
    ├── VariantSearch.tsx
    ├── SettingsPanel.tsx
    └── AdminPanel.tsx
```

### Dashboard Data Flow

All 13 panels read from a single endpoint: `GET /api/analysis/dashboard-data`. This endpoint:
1. Checks per-user cache (`dashboard_cache` table, fingerprint-keyed)
2. On cache miss: queries all 13 insight tables + analysis metadata
3. Returns a single JSON blob used by every panel

Panel components do NOT make individual API calls for insight data — everything comes from one response. Individual variant annotation details are fetched on demand via `POST /api/annotations/clinical-summary`.

### Theme System

`utils/theme.ts` centralizes all styling in dark/light mode:
- `getGlassBackground()`, `getTextPrimary()`, `getCardBackground()` etc.
- `getThemeClass(base, isDark)` maps 100+ Tailwind variants
- All panels import theme helpers — no ad-hoc Tailwind dark: classes

### API Integration

`frontend/src/lib/api.ts`:
```typescript
apiUrl('/endpoint')    // resolves NEXT_PUBLIC_API_URL or localhost:8000
apiFetch('/endpoint', { token })  // wraps fetch with auth headers
```

No Axios, no SWR, no React Query — plain `fetch()` with Bearer auth.

---

## 11. Security Model

- **JWT HS256** — 10-day token expiry (long for production). `SECRET_KEY` required at startup.
- **bcrypt** password hashing
- **Route protection** — `Depends(get_current_user)` on all routes except `/auth/login`, `/auth/register`, `/health`
- **Admin authorization** — `is_admin` flag checked per endpoint in `admin_routes.py`
- **Data isolation** — all queries scoped by `user_id`
- **CORS** — restricted to `localhost:3000`, `localhost:3001`, `127.0.0.1:3000`
- **Input validation** — Pydantic schemas for all request bodies
- **File upload** — VCF/CSV/TXT only, no size limit (consider adding)
- **Medical disclaimer** — shown on all insight panels (not a medical device)
