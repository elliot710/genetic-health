# Improvements & Refactoring Opportunities

> **Analysis date:** March 15, 2026
> **Scope:** Full-stack review of backend, frontend, database, infrastructure, and security

This document identifies concrete improvements organized by priority and effort. Each item explains the current state, the problem, and the recommended approach.

---

## Table of Contents

1. [Critical Issues (Fix Now)](#1-critical-issues)
2. [High-Priority Improvements (Next Sprint)](#2-high-priority-improvements)
3. [Medium-Priority Refactoring (Next Quarter)](#3-medium-priority-refactoring)
4. [Low-Priority Enhancements (Backlog)](#4-low-priority-enhancements)
5. [Architecture Debt Summary](#5-architecture-debt-summary)

---

## 1. Critical Issues

### 1.1 Hardcoded API Base URL in Frontend

**Current state:** Every `fetch()` call in the frontend uses `http://localhost:8000` as a hardcoded string.

**Problem:** This breaks in any non-local environment (staging, production, Docker networking changes). Despite `NEXT_PUBLIC_API_URL` being set in `docker-compose.yml`, it's not used in the actual code.

**Fix:**
```typescript
// Create frontend/src/lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
```
Replace all `fetch('http://localhost:8000/...')` with `fetch(apiUrl('/...'))`.

**Effort:** Low (2-3 hours)
**Impact:** High — prerequisite for any deployment beyond localhost

---

### 1.2 JWT in localStorage (XSS Vulnerability)

**Current state:** JWT token is stored in `localStorage` and sent as a `Bearer` token.

**Problem:** Any XSS vulnerability (third-party script, dependency compromise) can steal the token. With 10-day expiry, a stolen token gives prolonged unauthorized access to sensitive genetic data.

**Recommended approach:**
- Store JWT in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie set by the backend
- Backend sets the cookie on `/auth/login` response
- Frontend reads user state from `GET /auth/me` (cookie sent automatically)
- Reduce token expiry to 1-2 hours with a refresh token mechanism

**Effort:** Medium (1-2 days)
**Impact:** Critical — genetic data is highly sensitive PII

---

### 1.3 Secret Key Has Development Default

**Current state:** `core/auth.py` falls back to a hardcoded default `SECRET_KEY` if the environment variable isn't set.

**Problem:** If deployed without setting `SECRET_KEY`, all JWTs are signed with a known key. Anyone can forge admin tokens.

**Fix:** Remove the default. Fail loudly on startup if `SECRET_KEY` is not set:
```python
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable must be set")
```

**Effort:** Trivial (30 minutes)
**Impact:** Critical for any deployment

---

### 1.4 Missing Input Sanitization on File Upload

**Current state:** `VCFParser` processes user-uploaded files and extracts fields like rsid, chromosome, position directly from file content.

**Problem:** While SQL injection is prevented by SQLAlchemy's parameterized queries, there's no validation that rsid values match expected patterns (e.g., `rs\d+`), chromosome values are valid (1-22, X, Y, MT), or position values are reasonable integers. Malformed data could cause unexpected behavior in downstream analysis.

**Fix:** Add validation in `VCFParser`:
```python
import re
RSID_PATTERN = re.compile(r'^rs\d+$')
VALID_CHROMS = {'1','2',...,'22','X','Y','MT'}

def _validate_variant(self, variant: dict) -> bool:
    if not RSID_PATTERN.match(variant.get('rsid', '')):
        return False
    if variant.get('chromosome') not in VALID_CHROMS:
        return False
    # ... etc
```

**Effort:** Low (2-3 hours)
**Impact:** High — prevents garbage data from polluting the global marker catalog

---

## 2. High-Priority Improvements

### 2.1 Extract `Dashboard.tsx` — God Component

**Current state:** `Dashboard.tsx` is 1,900 LOC with 50+ hooks, hash-based routing, analysis polling, data fetching, deletion logic, notification system, and rendering of 13+ panels.

**Problem:** Extremely difficult to maintain, test, or reason about. Every change risks breaking something unrelated. A single state update re-renders the entire dashboard.

**Recommended decomposition:**
```
Dashboard.tsx (orchestrator, ~200 LOC)
├── hooks/useDashboardData.ts      — data fetching + refresh logic
├── hooks/useAnalysisPolling.ts    — analysis progress polling
├── hooks/useDashboardNavigation.ts — hash-based routing
├── components/DashboardSidebar.tsx — navigation sidebar
├── components/DashboardHeader.tsx  — user menu, theme toggle
├── components/DashboardContent.tsx — panel switcher (renders active panel)
├── components/OverviewTab.tsx      — charts, variant search, insights
└── components/DeleteDataDialog.tsx — confirmation dialog + deletion
```

**Effort:** High (3-5 days)
**Impact:** High — makes the dashboard maintainable and testable

---

### 2.2 Duplicate Data Fetching Across Panels

**Current state:** Multiple panels independently fetch `GET /api/analysis/dashboard-data`. During analysis polling, this endpoint is called on every status check. `Dashboard` fetches it, `page.tsx` fetches it, and some panels fetch it individually.

**Problem:** Redundant API calls. The backend queries all 13 insight tables every time, even when only one panel is visible.

**Recommended approach:**

**Option A (simpler):** Lift data fetching to `Dashboard` only. Pass data down as props (already partially done). Remove all panel-level fetches.

**Option B (better):** Use React Query / TanStack Query for:
- Automatic deduplication of identical requests
- Stale-while-revalidate caching
- Background refetching
- Per-panel cache keys (avoid re-querying all data when switching tabs)

**Option C (best, backend change):** Split `dashboard-data` into per-category endpoints:
```
GET /api/analysis/dashboard-data/health
GET /api/analysis/dashboard-data/drug-responses
GET /api/analysis/dashboard-data/ancestry
...
```
Each panel fetches only its own data. Combined with TanStack Query, this gives optimal performance.

**Effort:** Medium (Option A: 1 day, Option B: 2-3 days, Option C: 3-5 days)
**Impact:** High — reduces server load, improves perceived performance

---

### 2.3 Analysis Service is 2,700 LOC — Extract Insight Generators

**Current state:** `analysis_service.py` (2,698 LOC) contains the entire analysis pipeline: annotation fetching, scoring, and all 13 category-specific insight generation functions.

**Problem:** Single-file complexity makes it hard to understand, test, or modify individual categories without risk.

**Recommended decomposition:**
```
services/
├── analysis_service.py          (orchestrator only, ~500 LOC)
│   ├── process_analysis()       — main pipeline coordination
│   ├── _annotate_variants()     — Phase 2 annotation logic
│   └── _enrich_bigquery()       — Phase 3 BigQuery enrichment
├── shared_annotation_service.py (extracted from analysis_service.py, ~300 LOC)
├── insight_generators/
│   ├── __init__.py
│   ├── health_generator.py      — health_risks population
│   ├── drug_generator.py        — drug_responses population
│   ├── ancestry_generator.py    — ancestry_results population
│   ├── carrier_generator.py     — carrier_status population
│   ├── rare_mutation_generator.py
│   ├── trait_generator.py       — physical_traits, sports, nutrition, cognitive, personality
│   ├── methylation_generator.py
│   ├── detox_generator.py
│   └── wellness_generator.py
```

Each generator has a single `async def generate(session, analysis_id, annotations) -> List[Model]` function.

**Effort:** High (3-5 days)
**Impact:** High — testability, maintainability, ability to modify one category without risk

---

### 2.4 Replace Polling with WebSocket or SSE for Progress

**Current state:** `AnalysisProgressLoader` polls `GET /api/analysis/status/{id}` every 2 seconds.

**Problem:** Creates unnecessary load (a request every 2s per active user). Not scalable for multiple concurrent users. Also has a race condition where the poll might miss transient states.

**Recommended approach:** Server-Sent Events (SSE) — simpler than WebSocket, perfect for one-way server→client updates:

```python
# Backend
@router.get("/api/analysis/stream/{analysis_id}")
async def stream_progress(analysis_id: int):
    async def event_generator():
        while True:
            status = await get_analysis_status(analysis_id)
            yield f"data: {json.dumps(status)}\n\n"
            if status['status'] in ('completed', 'failed'):
                break
            await asyncio.sleep(1)
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

```typescript
// Frontend
const eventSource = new EventSource(`/api/analysis/stream/${id}`);
eventSource.onmessage = (event) => {
  const status = JSON.parse(event.data);
  setProgress(status);
};
```

**Effort:** Medium (1-2 days)
**Impact:** Medium — reduces server load, real-time feel

---

### 2.5 Error Handling: Silent Failures in Frontend

**Current state:** Most panel data fetches catch errors with `console.error()` only. Users see an empty panel with no indication that something failed.

**Problem:** Users can't distinguish "no data" from "fetch failed." No way to retry. Debug difficulty.

**Fix:** Add a standardized error state to each panel:
```typescript
// In shared.tsx
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 py-8 text-sm text-muted-foreground">
      <AlertCircle className="h-8 w-8 text-destructive" />
      <p>{message}</p>
      {onRetry && <Button variant="ghost" size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  );
}
```

Also consider a global error boundary with toast notifications.

**Effort:** Medium (1-2 days)
**Impact:** High for UX — users should know when something fails

---

### 2.6 Add Backend Integration Tests

**Current state:** No test files found in the backend. The only test file is `_test_graph.py` at the project root (appears to be a one-off script).

**Problem:** No automated tests for any API endpoint, service, or database operation. Changes carry high regression risk.

**Recommended approach:** Start with integration tests for the critical path:
```
tests/
├── conftest.py              — test DB setup, auth fixtures
├── test_auth.py             — register, login, me, change-password
├── test_upload.py           — VCF/CSV upload, variant dedup
├── test_analysis.py         — start, status, results, dashboard-data
├── test_annotations.py      — variant details, clinical summary
├── test_admin.py            — CRUD operations, permissions
└── test_variant_uploader.py — dedup logic unit tests
```

Use `pytest-asyncio` + `httpx.AsyncClient` + test database fixture.

**Effort:** High (1-2 weeks for core coverage)
**Impact:** Critical for maintainability and confidence in changes

---

## 3. Medium-Priority Refactoring

### 3.1 Create a Shared API Client in Frontend

**Current state:** Every component has raw `fetch()` calls with identical auth header logic, error handling, and JSON parsing.

**Problem:** Duplicated boilerplate across ~20 components. Inconsistent error handling. If auth flow changes (e.g., cookie-based), every file needs updating.

**Fix:** Create a small API client:
```typescript
// lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function api<T>(path: string, options?: RequestInit & { token?: string }): Promise<T> {
  const { token, ...fetchOptions } = options || {};
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  
  const response = await fetch(`${API_BASE}${path}`, { ...fetchOptions, headers });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, error.detail);
  }
  return response.json();
}
```

**Effort:** Medium (1-2 days)
**Impact:** Medium — reduces boilerplate, centralizes auth and error handling

---

### 3.2 Consolidate Duplicate/Legacy Components

**Current state:** Several components appear to be legacy versions kept alongside newer replacements:
- `FileUpload.tsx` (legacy) vs `ModernFileUpload.tsx` (current)
- `ThemeHelper.tsx` appears redundant with `utils/theme.ts`
- `GeneticAnnotation.tsx` appears to overlap with `VariantDetailDialog.tsx`

**Fix:** Audit each, confirm which is used, remove the dead files.

**Effort:** Low (1-2 hours)
**Impact:** Low — reduces confusion for new contributors

---

### 3.3 Type Safety for Backend JSON Columns

**Current state:** Twelve JSON columns on `SharedVariantAnnotation` (ensembl_data, clinvar_data, etc.) store arbitrary dicts. The `analysis_service.py` accesses these with deeply nested `.get()` chains.

**Problem:** No type validation on what goes into or comes out of these columns. A subtle API response change can silently corrupt data that's never deleted.

**Recommended approach:** Define TypedDict/Pydantic models for each JSON blob:
```python
class EnsemblAnnotation(TypedDict):
    found: bool
    data: list[dict]
    source: str

class ClinVarAnnotation(TypedDict):
    found: bool
    clinical_significance: str | None
    conditions: list[str]
    review_status: str | None
```

Use these in the service layer for serialization/deserialization. The DB column remains JSON, but the Python layer validates structure.

**Effort:** Medium (2-3 days)
**Impact:** Medium — prevents silent data corruption, improves IDE autocomplete

---

### 3.4 Database: Add Soft Delete for Analyses

**Current state:** Deleting an analysis runs batched hard-deletes across many tables. The instant UI feedback uses a `status='deleted'` marker, but the actual records are physically removed.

**Problem:** No way to recover accidentally deleted data. The background deletion process is complex (50K row batches).

**Recommended approach:** Add `deleted_at` timestamp to `genetic_analyses`. Filter by `deleted_at IS NULL` in all queries. Run a periodic cleanup job (nightly) for hard deletes of analyses deleted more than 30 days ago.

**Effort:** Medium (1-2 days)
**Impact:** Medium — data safety, simpler delete flow

---

### 3.5 Decouple `pharmgkb_data` Column Name

**Current state:** The `shared_variant_annotations.pharmgkb_data` column stores ClinPGx data. Code comments say "column kept as pharmgkb_data for backward compat." The service layer has special-case code:
```python
data = getattr(annotation, 'clinpgx_data', None)  # doesn't exist
if data is None:
    data = getattr(annotation, 'pharmgkb_data', None)  # actual column
```

**Problem:** Confusing for anyone reading the code. Source of potential bugs if someone creates a `clinpgx_data` column thinking it doesn't exist.

**Fix:** Create an Alembic migration to rename the column:
```python
op.alter_column('shared_variant_annotations', 'pharmgkb_data', new_column_name='clinpgx_data')
```
Update all references in `analysis_service.py`, `annotation_routes.py`, etc.

**Effort:** Low (2-3 hours)
**Impact:** Low — code clarity

---

### 3.6 N+1 Query Risk in Dashboard Data Endpoint

**Current state:** `GET /api/analysis/dashboard-data` loads all 13 insight tables in separate queries, then for each variant-related record, may access `analysis_variant.marker.rsid` through relationship lazy loading.

**Problem:** Potential N+1 queries when accessing marker properties through AnalysisVariant proxy properties, especially in loops.

**Fix:** Ensure all relationship-heavy queries use `selectinload` or `joinedload`:
```python
variants = await session.execute(
    select(AnalysisVariant)
    .where(AnalysisVariant.analysis_id == analysis_id)
    .options(selectinload(AnalysisVariant.marker))
)
```

**Effort:** Low (audit and add eager loading options)
**Impact:** Medium — can significantly improve dashboard load time

---

### 3.7 Rate Limit ClinPGx More Aggressively

**Current state:** ClinPGx is configured at 1.0 req/s in `api_endpoints.py`, but the actual server returns 429 errors. The comment says "server returns 429 at higher."

**Problem:** The annotation pipeline retries with exponential backoff, but failed ClinPGx calls slow down the entire analysis.

**Fix:**
- Reduce ClinPGx rate limit to 0.5 req/s (1 request per 2 seconds)
- Consider making ClinPGx calls fire-and-forget (don't block the main annotation pipeline)
- Back-fill ClinPGx data asynchronously after the main analysis completes

**Effort:** Low (1 hour)
**Impact:** Medium — faster analysis completion

---

## 4. Low-Priority Enhancements

### 4.1 Add OpenTelemetry Tracing

**Current state:** Logging is done with Python `logging` module. Per-analysis logs are collected in-memory by `JobLogCollector`.

**Improvement:** Add OpenTelemetry tracing spans around:
- Analysis pipeline phases
- External API calls (with status codes, response times)
- Database queries (with table names and row counts)
- File parsing duration

This gives visibility into bottlenecks without digging through logs.

**Effort:** Medium (2-3 days)
**Impact:** Medium — operational visibility

---

### 4.2 Use Alembic's Multi-Head Strategy or Squash Migrations

**Current state:** 38 migrations with several `merge` migrations to resolve multiple heads.

**Problem:** Migration history is complex. New developers need to understand the full evolution. Some intermediate migrations may no longer be meaningful.

**Fix:** Once schema is stable, squash all migrations into a single "baseline" migration. Keep the `init-db.sql` for fresh installs.

**Effort:** Low (1-2 hours, but requires testing)
**Impact:** Low — developer experience

---

### 4.3 Consider Materialized Views for Dashboard Data

**Current state:** `dashboard-data` endpoint runs 13+ separate queries to assemble the response.

**Improvement:** Create a materialized view or denormalized dashboard cache table:
```sql
CREATE MATERIALIZED VIEW mv_dashboard_summary AS
SELECT analysis_id,
  (SELECT count(*) FROM health_risks WHERE ...) as health_risk_count,
  (SELECT json_agg(...) FROM health_risks WHERE ...) as health_risks,
  ...
```
Refresh after analysis completion. The dashboard-data endpoint reads from the view instead of running 13 queries.

**Effort:** Medium (2-3 days)
**Impact:** Medium — faster dashboard loads for large datasets

---

### 4.4 Frontend: Code Splitting for Category Panels

**Current state:** All 13 panels are imported and bundled together in `Dashboard.tsx`, even though only one is visible at a time.

**Improvement:** Use `React.lazy()` + `Suspense` for category panels:
```typescript
const HealthPanel = React.lazy(() => import('./categories/HealthPanel'));
const DrugResponsesPanel = React.lazy(() => import('./categories/DrugResponsesPanel'));
// ...
```

**Effort:** Low (1-2 hours)
**Impact:** Low — reduces initial bundle size, improves FCP

---

### 4.5 Add Database Backup Automation

**Current state:** One manual backup file exists (`backups/genetic_health_db_backup_20260313.dump`).

**Improvement:** Add a cron job or Docker sidecar for automated daily backups:
```yaml
# docker-compose.yml
backup:
  image: postgres:15
  volumes:
    - ./backups:/backups
  entrypoint: /bin/sh -c 'while true; do pg_dump -U postgres -h postgres genetic_health_db > /backups/$(date +%Y%m%d).dump; sleep 86400; done'
  depends_on:
    - postgres
```

**Effort:** Low (1 hour)
**Impact:** Medium — data safety

---

### 4.6 Move from `@app.on_event` to Lifespan API

**Current state:** `main.py` uses deprecated `@app.on_event("startup")` and `@app.on_event("shutdown")`.

**Fix:** Use FastAPI's lifespan context manager (recommended since FastAPI 0.93+):
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    queue = get_analysis_queue()
    await queue.start()
    yield
    # Shutdown
    await queue.stop()

app = FastAPI(lifespan=lifespan)
```

**Effort:** Low (1 hour)
**Impact:** Low — future-proofs against FastAPI deprecation warnings

---

### 4.7 Add Health Check Authentication

**Current state:** `GET /health` endpoint is unauthenticated and returns database connectivity status with error details.

**Problem:** In production, exposing database error messages to unauthenticated users is an information disclosure risk.

**Fix:** Keep `GET /health` for Docker/monitoring (return only `{"status": "healthy"}` or `{"status": "unhealthy"}`). Move detailed health info to an authenticated admin endpoint.

**Effort:** Trivial (30 minutes)
**Impact:** Low but good practice

---

### 4.8 Frontend: Add Loading Skeletons to Panels

**Current state:** Panels show either data or nothing while loading.

**Improvement:** Use the existing `skeleton.tsx` shadcn component to show loading skeletons that match the panel layout shape.

**Effort:** Low (2-3 hours)
**Impact:** Low — perceived performance improvement

---

## 5. Architecture Debt Summary

### Debt by Severity

| Severity | Count | Items |
|----------|-------|-------|
| **Critical** | 4 | Hardcoded API URL, JWT in localStorage, Secret Key default, File input validation |
| **High** | 6 | God component, duplicate fetching, analysis_service.py size, no tests, error handling, polling |
| **Medium** | 7 | API client, JSON type safety, soft delete, pharmgkb rename, N+1 queries, ClinPGx rate limit, legacy components |
| **Low** | 8 | Tracing, migration squash, materialized views, code splitting, backups, lifespan API, health check, skeletons |

### Technical Debt Hotspots (by file)

```
🔴 Critical:   frontend/src/app/page.tsx (hardcoded URL, JWT in localStorage)
🔴 Critical:   backend/core/auth.py (SECRET_KEY default)
🟡 High:       frontend/src/components/Dashboard.tsx (1900 LOC god component)
🟡 High:       backend/services/analysis_service.py (2698 LOC, 13 generators mixed in)
🟡 High:       backend/api/annotation_routes.py (979 LOC, complex response assembly)
🟡 High:       backend/api/variant_routes.py (853 LOC, mixed concerns)
🟠 Medium:     backend/db/models.py (835 LOC, could split by domain)
🟠 Medium:     frontend/src/utils/theme.ts (400 LOC, 100+ class mappings)
```

### What's Working Well

The architecture has several strong design decisions that should be preserved:

1. **Deduplication architecture** — The shared annotation cache is a smart design that avoids redundant API calls. The separation between global markers and user-specific variants is excellent.

2. **Multi-source data integration** — The layered approach (local PG first → remote API fallback → BigQuery enrichment) is well-designed. Each data source has its own service with clean interfaces.

3. **Background job queue** — The `AnalysisQueue` with concurrency limits and stale job recovery is production-ready.

4. **Admin discovery pipeline** — The auto-discovery of markers with admin approval is a clever way to grow the variant catalog organically.

5. **Category rules engine** — `CategoryRule` table provides configurable, priority-ordered rules for variant categorization without code changes.

6. **DI container** — Simple but effective. The transient registration for API services prevents cache leaking between users.

7. **Comprehensive data model** — 13 category tables each store rich, typed data. The insight tables have well-defined schemas.

8. **Theme centralization** — Single source of truth for all dark/light mode styling.

9. **Shared components** — `shared.tsx` with severity mappers and reusable components ensures consistent UX across all 13 panels.

10. **Progress tracking** — Four-phase weighted model gives users meaningful progress indication during long analyses.
