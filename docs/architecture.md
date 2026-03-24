# Genetic Health Analysis Toolkit — Architecture

> Last updated: 2025  
> Status: Production-like development environment  
> Stack: FastAPI · SQLAlchemy 2.0 async · PostgreSQL · Next.js 15 · Docker

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Container Architecture](#2-container-architecture)
3. [Backend Structure](#3-backend-structure)
4. [Frontend Structure](#4-frontend-structure)
5. [Database Schema](#5-database-schema)
6. [Analysis Pipeline](#6-analysis-pipeline)
7. [Insight Generation Pipeline](#7-insight-generation-pipeline)
8. [External Data Sources](#8-external-data-sources)
9. [Authentication & Security](#9-authentication--security)
10. [Key Design Decisions](#10-key-design-decisions)

---

## 1. System Overview

A full-stack genomics analysis platform that ingests personal DNA data (VCF or CSV), annotates every genetic variant against multiple clinical and population databases, then uses a rule-based insight generation pipeline to produce actionable health reports across 14 categories.

```
┌───────────────────────────────────────────────────────────────┐
│  User                                                         │
│   Upload VCF/CSV ──► Annotation Pipeline ──► 14 Insight Panels│
│                       (async worker)         (interactive UI) │
└───────────────────────────────────────────────────────────────┘
```

**Current data scale (single user analysis):**
- 731,703 genetic markers stored
- 714,586 shared variant annotations with Ensembl data
- ~4.5 GB shared annotation cache (16 GB with 1000 Genomes)
- 237,000+ variant mappings across all categories

---

## 2. Container Architecture

```
docker-compose.yml
│
├─ frontend    (Next.js 15, port 3000)   — Turbopack dev server
├─ backend     (FastAPI, port 8000)      — API server only, no analysis
├─ worker      (Python)                  — Runs analysis jobs from DB queue
└─ postgres    (PostgreSQL 15, port 5432)— Single shared database
```

### Service Separation Philosophy

Analysis work was intentionally moved from FastAPI to a separate `worker` service. The FastAPI process only handles HTTP requests; the worker polls the `worker_jobs` table and executes full analysis pipelines without touching the API event loop. This prevents long-running genomic computations from blocking API responses.

### URLs & Credentials (Development)

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API + Docs | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

Login: `elliotalderson710@gmail.com` / `Victor123!`  
Login field is `username` (not `email`) — auth uses OAuth2PasswordRequestForm.

---

## 3. Backend Structure

```
backend/
├── main.py                    # FastAPI app: CORS, router mounts, startup/shutdown lifecycle
├── worker.py                  # Worker process: polls worker_jobs, runs analysis
├── api/                       # 9 route handlers
│   ├── auth_routes.py         # POST /auth/login, /auth/register, GET /auth/me
│   ├── upload_routes.py       # POST /upload (VCF/CSV), DELETE /upload/data
│   ├── analysis_routes.py     # /api/analysis — start, status, results, dashboard-data
│   ├── annotation_routes.py   # /api/annotations — variant details, clinical summary, literature
│   ├── variant_routes.py      # /api/variants — multi-source lookup, saved variants
│   ├── admin_routes.py        # /api/admin — users, panels, markers, discoveries
│   ├── insights_routes.py     # /api/insights — AI-generated text summaries (Gemini)
│   ├── health_routes.py       # /health — health check
│   └── notification_routes.py # /ws/notifications — WebSocket + REST notifications
├── services/                  # 30+ service modules
│   ├── analysis_service.py    # Orchestrator: coordinates annotation + insight phases
│   ├── variant_loader.py      # Load variants from DB into VariantLite objects + gene map
│   ├── annotation_coordinator.py # Decides reuse vs new API call for each variant
│   ├── shared_annotation_service.py # Reads/writes SharedVariantAnnotation cache
│   ├── insight_dispatcher.py  # Dispatches all 16 generators in correct order
│   ├── insight_generators/    # 16 generators (see §7)
│   ├── genetic_api_service.py # Multi-API hub (Ensembl, ClinVar, PharmGKB, SNPedia, LitVar)
│   ├── ensembl_vep_local.py   # Local VEP: SQLite cache + VCF file scan fallback
│   ├── clinvar_local.py       # ClinVar PostgreSQL reader (2.6 GB table)
│   ├── gnomad_local.py        # gnomAD PostgreSQL + CADD SQLite cache reader
│   ├── gnomad_bigquery.py     # gnomAD Google BigQuery fallback
│   ├── thousand_genomes_local.py # 1000 Genomes PostgreSQL reader (16 GB table)
│   ├── local_annotation.py    # Aggregates all local sources into unified annotation dict
│   ├── auto_categorizer.py    # Auto-assigns categories to variants from annotation signals
│   ├── multi_source_categorizer.py # Merges categorizer results into VariantMapping rows
│   ├── scoring_engine.py      # Composite pathogenicity scoring (ClinVar + gnomAD + AM)
│   ├── knowledge_graph.py     # Builds gene/condition relationship graphs
│   ├── discovery_service.py   # Auto-discovers new panel markers (pending_discoveries table)
│   ├── insights_service.py    # Gemini LLM summaries (separate from rule-based generators)
│   ├── bq_public.py           # Google BigQuery public genomics datasets (ChEMBL, FDA)
│   ├── user_service.py        # User CRUD, password hashing, JWT creation
│   ├── notification_service.py # Push notifications via WebSocket + DB
│   ├── job_logs.py            # Per-job structured logging into genetic_analyses.job_logs
│   └── api_endpoints.py       # Centralized API endpoint config + rate limits
├── core/
│   ├── config.py              # Settings (Pydantic BaseSettings) — env vars
│   ├── auth.py                # JWT HS256, 10-day expiry, bcrypt password hashing
│   ├── container.py           # Lightweight DI container (singletons + transients)
│   ├── exceptions.py          # Custom exception hierarchy
│   └── telemetry.py           # OpenTelemetry tracing configuration
└── db/
    ├── database.py            # Async SQLAlchemy 2.0 engine + session factory
    ├── models.py              # All ORM models (~500 lines)
    ├── schemas.py             # Pydantic request/response schemas
    ├── annotation_schemas.py  # TypedDicts for annotation JSON shapes
    └── datasource_models.py   # ORM models for local data source tables (ClinVar, gnomAD, etc.)
```

### Startup Lifecycle (`main.py` lifespan)

1. `init_db()` — Ensure schema exists
2. Install `JobLogHandler` on analysis-related loggers
3. Validate ClinVar PG availability (instant row count)
4. Validate gnomAD PG availability (instant row count)
5. Start gnomAD SQLite CADD cache preload in background task
6. Validate 1000 Genomes PG availability
7. Start Ensembl VEP SQLite cache preload in background task
8. Schedule nightly purge task (hard-deletes soft-deleted analyses > 30 days)
9. Schedule analysis completion watcher (polls every 12s, creates notifications)

---

## 4. Frontend Structure

```
frontend/src/
├── app/
│   ├── layout.tsx             # Root layout
│   ├── page.tsx               # SPA entry: AuthForm → FileUpload → Dashboard flow
│   └── globals.css
├── components/
│   ├── Dashboard.tsx          # Navigation + lazy-loaded panel orchestrator (14 tabs)
│   ├── AuthForm.tsx           # Login/register with dark/light mode toggle
│   ├── FileUpload.tsx         # Drag-drop VCF/CSV with chunked upload + progress
│   ├── VariantSearch.tsx      # Direct rsid/gene lookup with annotation display
│   ├── SettingsPanel.tsx      # User profile, password change, data deletion
│   ├── SmartInsights.tsx      # Gemini AI insight panel (per section)
│   ├── GeneticAnnotation.tsx  # Standalone annotation viewer (unused in main flow)
│   ├── KnowledgeGraph.tsx     # Gene/condition relationship graph visualizer
│   ├── AnalysisProgressLoader.tsx # Polling progress bar during analysis
│   ├── categories/            # 15 files: 13 active panels + shared utilities
│   │   ├── shared.tsx         # CategoryHeader, SectionCard, VariantLinks, VariantDetailTrigger
│   │   ├── types.ts           # TypeScript interfaces for all 14 category data shapes
│   │   ├── VariantDetailDialog.tsx  # Annotation overlay (Ensembl, ClinVar, gnomAD, etc.)
│   │   ├── GenomicCharts.tsx  # Recharts-based: CapacityChart, DrugResponseChart, TraitRadarChart
│   │   ├── ResearchLinks.tsx  # External links (dbSNP, ClinVar, SNPedia, PubMed)
│   │   ├── HealthPanel.tsx    # Health risks + risk level badges
│   │   ├── DrugResponsesPanel.tsx  # Drug response predictions + metabolism charts
│   │   ├── AncestryPanel.tsx  # Population composition + haplogroups
│   │   ├── CarrierStatusPanel.tsx  # Autosomal recessive/dominant carrier flags
│   │   ├── FoodNutritionPanel.tsx  # Nutrient metabolism + dietary recommendations
│   │   ├── SportsPanel.tsx    # Athletic performance genetic factors
│   │   ├── PhysicalTraitsPanel.tsx # Physical characteristic predictions
│   │   ├── IntelligencePanel.tsx   # Cognitive profile + percentile scores
│   │   ├── PersonalityPanel.tsx    # Personality traits + behavioral insights
│   │   ├── WellnessPanel.tsx  # Wellness metric optimization
│   │   ├── MethylationPanel.tsx    # Methylation cycle capacity
│   │   ├── DetoxPanel.tsx     # Detoxification phase capacity
│   │   ├── RareMutationsPanel.tsx  # Clinically significant rare variants
│   │   └── UncommonMutationsPanel.tsx # Low-frequency variants (0.1%–5%)
│   ├── admin/
│   │   └── AdminPanel.tsx     # User management, panel marker CRUD, discovery approvals
│   ├── dashboard/             # Sub-components for dashboard navigation
│   └── ui/                    # shadcn/ui primitives (button, dialog, card, badge, etc.)
├── utils/
│   └── theme.ts               # Centralized glassmorphism theme (getGlassBackground, etc.)
├── hooks/
│   └── use-mobile.ts          # Mobile viewport detection hook
└── lib/
    └── utils.ts               # cn() utility (clsx + tailwind-merge)
```

### Panel Data Flow

Each category panel follows the same pattern:
```
Dashboard renders panel ──► panel fetches GET /api/analysis/dashboard-data?section=X
                            ──► deserializes typed response
                            ──► renders with glassmorphism theme
                            ──► VariantDetailDialog on click (fetches /api/annotations/variant/{rsid})
```

All API calls use direct `fetch()` with `Authorization: Bearer {token}` header. No API client abstraction.

---

## 5. Database Schema

### Core Tables

| Table | Size | Purpose |
|-------|------|---------|
| `users` | — | User accounts (is_admin, is_verified) |
| `genetic_analyses` | — | Analysis records (status, progress, job_logs JSONB) |
| `worker_jobs` | — | Job queue for worker process |
| `notifications` | — | User notifications (WebSocket + REST) |

### Variant Deduplication Architecture

| Table | Size | Purpose |
|-------|------|---------|
| `genetic_markers` | 98 MB | Global catalog of all unique variants (rsid, chr, pos, ref, alt). Never deleted. 731K rows. |
| `analysis_variants` | 367 MB | Links analysis → marker + user genotype. Cascade-deleted with analysis. |
| `shared_variant_annotations` | 4.5 GB | External API results per marker (13 JSON columns). Never deleted — accumulates as shared cache. 714K annotated rows. |
| `variant_annotations` | 133 MB | User-specific references to shared annotations. |
| `variant_lookup_cache` | — | Processed variant response cache with usage counting. |

This deduplication means repeated uploads of the same rsid across all users never re-fetches external APIs.

### Insight Tables (all cascade-delete on analysis)

All 14 insight tables follow the same pattern:

| Table | Key Columns |
|-------|------------|
| `health_risks` | condition, risk_level (String), risk_score (String "0.8"), associated_variants (JSON array), recommendations (JSON array) |
| `drug_responses` | drug, metabolism_type, response_level, variants_involved (JSON array) |
| `physical_traits` | trait, result, confidence, associated_variants (JSON array) |
| `nutrition_traits` | nutrient, sensitivity_level, dietary_recommendations (JSON array) |
| `sports_performance` | sport_type, advantage_level, sport_recommendations (JSON array) |
| `cognitive_profiles` | cognitive_area, performance_level, percentile, enhancement_suggestions (JSON array) |
| `personality_traits` | trait_name, trait_level, behavioral_insights (JSON array) |
| `ancestry_results` | population, composition (JSON), maternal_haplogroup (JSON), neanderthal_variants (JSON) |
| `carrier_status` | condition, carrier_type, associated_variants (JSON array) |
| `wellness_metrics` | metric, optimization_level, lifestyle_recommendations (JSON array) |
| `methylation_profiles` | pathway, capacity_level, supplement_recommendations (JSON array) |
| `detoxification_profiles` | phase, capacity, support_recommendations (JSON array) |
| `rare_mutations` | gene, condition, clinical_significance, clinical_actions (JSON array), monitoring_recommendations (JSON array) |
| `uncommon_mutations` | gene, consequence_type, lifestyle_implications (JSON array), monitoring_suggestions (JSON array) |

### Mapping Tables

| Table | Size | Purpose |
|-------|------|---------|
| `variant_mappings` | 126 MB | Replaces static registry. Stores category↔variant mappings. 237K rows. |
| `category_rules` | — | Templates for auto-categorizer output shapes |
| `pending_discoveries` | — | Auto-discovered markers awaiting admin approval |

`variant_mappings` schema:
```
category  | map_type | key (rsid or gene) | data (JSON) | sources (JSON array)
```

**Distribution (current DB):**
```
uncommon  | rsid: 224,115     health     | rsid: 9,435
rare      | rsid:   4,974     drug       | rsid:   884
carrier   | rsid:     669     cognitive  | rsid:   440 + gene: 12
physical  | rsid:     539     sports     | rsid:   414
nutrition | rsid:     385     detox      | rsid:   231 + gene: 10
methylation| rsid:   243     wellness   | rsid:   309
personality| rsid:   165     ancestry   | rsid:   137
```

### Local Data Source Tables (datasource_models.py)

| Table | Size | Content |
|-------|------|---------|
| `thousand_genomes_variants` | 16 GB | 1000 Genomes Phase 3 population allele frequencies |
| `clinvar_variants` | 2.6 GB | ClinVar variant clinical significance annotations |
| `clinvar_gene_stats` | 8 MB | Per-gene pathogenicity statistics from ClinVar |
| `clinvar_gene_conditions` | 1 MB | Gene → condition associations from ClinVar |
| `ensembl_genes` | 7 MB | Gene symbols, biotypes, chromosomal positions |
| `ancestry_aims_panel` | 123 MB | Ancestry Informative Markers panel |

---

## 6. Analysis Pipeline

```
POST /upload
    │
    ▼
variant_uploader.py
    │  parse VCF/CSV lines into (rsid, chr, pos, ref, alt, genotype) tuples
    │  batch 1000 at a time
    │  upsert into genetic_markers (dedup by rsid)
    │  insert into analysis_variants (analysis_id, marker_id, genotype)
    │
    ▼
worker_jobs INSERT (analysis_id, params)
    │
    ▼ (worker process picks up job)
    │
analysis_service.py — process_analysis()
    │
    ├─ Phase 1 (0%–2%):   variant_loader.py
    │                      Load VariantLite objects from DB
    │                      Build rsid_gene_map from ClinVar (rsid → gene)
    │                      Correct ref alleles from local sources
    │
    ├─ Phase 2 (2%–30%):  annotation_coordinator.py
    │                      For each variant:
    │                        Check SharedVariantAnnotation for existing data
    │                        If exists + fresh: reuse (no API call)
    │                        If missing/stale: call genetic_api_service.py
    │                          → Ensembl VEP (local SQLite cache first, remote fallback)
    │                          → ClinVar local PG
    │                          → gnomAD local PG + CADD cache
    │                          → 1000 Genomes local PG
    │                          → PharmGKB/ClinPGx API
    │                          → SNPedia API
    │                          → LitVar API
    │                      Store result in shared_variant_annotations
    │
    ├─ Phase 3 (30%–90%): bq_public.py (optional BigQuery enrichment)
    │                      → ChEMBL drug mechanisms
    │                      → FDA drug interaction labels
    │                      → AlphaFold protein structures
    │
    ├─ Phase 3.5:          multi_source_categorizer.py
    │                      auto_categorizer.py assigns categories from annotation signals
    │                      Results stored as new VariantMapping rows
    │
    └─ Phase 4 (90%–100%): insight_dispatcher.py
                           Dispatch all 16 insight generators in sequence
                           Populate 14 insight tables
                           Update analysis_status = 'completed'
```

### Resume Logic

If the worker crashes mid-analysis, it can resume from the last completed phase by reading `genetic_analyses.current_step`:

```
'initializing'         → restart from Phase 1
'annotating_variants'  → restart annotation (Phase 2) — NOTE: cannot tell if partial
'enriching_data'       → skip to Phase 3
'generating_insights'  → skip to Phase 4
'completed'            → no-op
```

---

## 7. Insight Generation Pipeline

### Generator Context

Before dispatching generators, `insight_dispatcher.py` builds a shared `GeneratorContext`:
- All `VariantLite` objects for the analysis
- All `AnnotationResult` objects (pre-fetched)
- `VariantProfile` per rsid (pre-computed: ref allele, gene, consequence, impact, frequency, is_hom_ref, is_het, composite score, pathogenicity score)
- `rsid_gene_map` (ClinVar rsid → gene symbol)
- `variant_profiles` dict (rsid → VariantProfile)

### The 16 Generators

| Generator | Table | Method |
|-----------|-------|--------|
| `health.py` | `health_risks` | `generate_from_maps()` with `assess_risk_level()` |
| `drug_response.py` | `drug_responses` | Custom gene-based multi-drug loop |
| `physical_traits.py` | `physical_traits` | `generate_from_maps()` + `boost_if_pathogenic()` |
| `nutrition.py` | `nutrition_traits` | `generate_from_maps()` + `boost_if_pathogenic()` |
| `sports.py` | `sports_performance` | `generate_from_maps()` + `boost_if_pathogenic()` |
| `cognitive.py` | `cognitive_profiles` | Custom percentile model (±10 per zygosity) |
| `personality.py` | `personality_traits` | `generate_from_maps()` + `boost_if_pathogenic()` |
| `ancestry.py` | `ancestry_results` | Custom AIMs genotype likelihood + haplogroup extraction |
| `carrier.py` | `carrier_status` | Custom zygosity classification + ClinVar discovery |
| `wellness.py` | `wellness_metrics` | `generate_from_maps()` + `boost_if_pathogenic()` |
| `methylation.py` | `methylation_profiles` | `generate_from_maps()` + `boost_if_pathogenic()` |
| `detox.py` | `detoxification_profiles` | `generate_from_maps()` + `boost_if_pathogenic()` |
| `rare_mutations.py` | `rare_mutations` | Custom ClinVar significance inspection (<1% frequency) |
| `uncommon_mutations.py` | `uncommon_mutations` | Custom consequence filter, capped at 500 results |

### generate_from_maps() Core Logic

All map-driven generators share the same 3-step variant processing loop in `base.py`:

```
for variant in ctx.variants:
    1. Skip if no-call genotype (./. or .|.)
    2. Skip if homozygous reference (user carries no risk allele)
    3. PATH A — RSID match (rsid in rsid_map):
         a. Skip if ClinVar-confirmed benign
         b. For non-indels: verify user allele matches expected risk allele
              (includes strand-flip complement fallback)
         c. For indels: SKIP allele verification — accepted on rsid presence alone
         d. Build insight from mapping data
    4. PATH B — Gene match (Ensembl/ClinVar gene in gene_map):
         a. Skip if ClinVar-confirmed benign
         b. Require HIGH or MODERATE VEP consequence (or pathogenic ClinVar)
         c. Build insight from gene mapping data
```

### Risk Assessment Logic

`assess_risk_level()` in `base.py` blends three signals:

1. **Pathogenicity composite score** (0.0–1.0, from scoring_engine.py):
   - ≥ 0.80 → `high`
   - ≥ 0.60 → `high` if multiplier ≥ 2.0, else `moderate`
   - ≥ 0.30 → `moderate` if multiplier ≥ 2.0, else `average`
   - < 0.30 → fallback to multiplier-only thresholds

2. **Risk multiplier** (from `VariantMapping.data['risk_multiplier']`):
   - ≥ 1.7 → at least `moderate`  
   - ≥ 1.2 → at least `low`

3. **Zygosity adjustment** (±1 step on severity ladder):
   - Homozygous alt → +1 step
   - Heterozygous → no change
   - Homozygous ref → −1 step (but only if ref_allele is known)

**Severity ladder:** `low → average → moderate → high → very_high`

**Risk-to-score:** `low=0.2, average=0.4, moderate=0.6, high=0.8, very_high=0.95`

### Scoring Engine (`scoring_engine.py`)

Computes composite pathogenicity score per variant from:
- ClinVar clinical significance classification
- gnomAD allele frequency (rare = more concerning)
- AlphaMissense missense pathogenicity score
- CADD PHRED score
- VEP consequence severity

Used in `analysis_routes.py /api/analysis/dashboard-data` and `annotation_routes.py /api/annotations/variant/{rsid}`.

---

## 8. External Data Sources

### Local (PostgreSQL/SQLite — no API cost)

| Source | Storage | Size | Content |
|--------|---------|------|---------|
| ClinVar | PostgreSQL | 2.6 GB | Clinical significance for 2.6M variants |
| gnomAD | PostgreSQL | varies | Population allele frequencies |
| gnomAD CADD | SQLite | varies | CADD pathogenicity scores (tabix-indexed TSV) |
| 1000 Genomes | PostgreSQL | 16 GB | Phase 3 allele frequencies across 26 populations |
| Ensembl VEP | SQLite cache + VCF | varies | Variant consequence & gene annotations |
| AlphaMissense | local file | varies | Missense variant pathogenicity predictions |
| Ancestry AIMs | PostgreSQL | 123 MB | Ancestry Informative Markers panel |

### Remote APIs (rate-limited)

| Source | Rate Limit | Purpose |
|--------|-----------|---------|
| Ensembl REST | fallback only | VEP consequence when local cache misses |
| ClinPGx/PharmGKB | 2.0 req/s | Pharmacogenomic drug-gene interactions |
| SNPedia | moderate | Phenotype associations, wiki-style |
| LitVar/PubMed | moderate | Literature citations per variant |
| NCBI | 10 req/s (with API key) | Gene/variant metadata |

### Optional Cloud (BigQuery)

Requires GOOGLE_APPLICATION_CREDENTIALS:
- gnomAD BigQuery (fallback when local PG empty)
- ChEMBL drug mechanisms
- FDA drug interaction labels
- AlphaFold protein structure data

---

## 9. Authentication & Security

- **Algorithm**: JWT HS256 with 10-day expiry
- **Transport**: `Authorization: Bearer {token}` header (frontend) / can be HttpOnly cookie
- **Password hashing**: bcrypt via `passlib`
- **Route protection**: All routes use `Depends(get_current_user)` except `/auth/login`, `/auth/register`, `/health`
- **CORS**: Allows `localhost:3000` and `localhost:3001` only
- **Admin guard**: `Depends(require_admin)` on all `/api/admin/*` routes

---

## 10. Key Design Decisions

### Shared Annotation Cache (Deduplication)

`shared_variant_annotations` accumulates API responses forever and is never deleted, even when users delete their data. This means:
- Repeated analyses of common variants (rs53576, APOE variants) never re-fetch
- Two users uploading 23andMe data sharing millions of common variants get instant annotation reuse
- 714K rows already cached after a handful of analyses

Trade-off: Table grows indefinitely and currently sits at 4.5 GB with 13 JSON columns (each can be 10–500 KB per row).

### Worker/API Separation

The worker and API run as separate Docker services reading from the same database. The API creates a `worker_jobs` row; the worker polls and executes. This means:
- No async event loop contamination with long-running analysis code
- Worker can be scaled independently
- Crash in worker doesn't take down the API
- Trade-off: No in-process job cancellation; must set DB flag and worker must poll it

### VariantMapping Replaces Static Registry

Before migration 014, a static `variant_registry.py` file contained hardcoded rsid→condition maps. This was replaced by the `variant_mappings` table which:
- Can be updated at runtime via admin panel
- Supports auto-discovery of new markers via `discovery_service.py`
- Enables per-source tracking (`sources` JSON column)
- Trade-off: Admin panel needed for all mapping changes; no migration history without Alembic

### Insight Generators vs LLM Insights

Two separate insight systems exist:
1. **Rule-based generators** (`insight_generators/`) — populate DB tables deterministically
2. **Gemini AI summaries** (`insights_service.py`) — generate on-demand text summaries fetched by `SmartInsights.tsx`

These systems are independent. The rule-based pipeline runs once per analysis; LLM summaries are generated lazily when the user opens a panel and cached in `ai_insight_cache`.
