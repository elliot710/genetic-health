---
title: God-File Splits (subagent-sized) - Plan
type: refactor
date: 2026-07-11
topic: god-file-splits
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
origin: docs/plans/2026-07-03-001-refactor-full-app-refactor-plan.md
---

# God-File Splits (subagent-sized) - Plan

## Goal Capsule

- **Objective:** Execute the deferred behavior-preserving god-file splits from the full-app refactor plan (its U15, U16, U18, U19, U20), re-decomposed into **subagent-sized sub-units** so no single unit exhausts a worker's budget mid-split. Each of the original units was one 2600–3600-line file split that repeatedly hit the session limit when attempted whole.
- **Authority:** This plan re-scopes only the *decomposition granularity* of origin units U15/U16/U18/U19/U20. It does not change their intent (behavior-preserving structural splits) or add new behavior. Origin: `docs/plans/2026-07-03-001-refactor-full-app-refactor-plan.md`.
- **Already done (out of scope):** origin U10 (DI container deleted), U11 (dead annotation layer removed), U13 (backwards-dep + DRY), U14 (`base.py` already split to `base/`). U15 step 1 (admin negative-authz gate `backend/tests/test_admin_route_authz.py`) is committed and is the safety net for Phase A.
- **Verification spine:** Backend units are proven behavior-preserving by the pytest suite (baseline **1777 passed**) + the insight characterization snapshot (`backend/tests/test_insight_snapshot.py`) + the admin negative-authz gate. Frontend has **no test harness** — those units are verified only by `pnpm build` + `pnpm lint` (currently **0 errors**) + code-level review.
- **Stop conditions:** Stop and surface if (a) a split cannot preserve the public import surface without a consumer edit the plan didn't anticipate, (b) a "pure move" would require a behavior change to compile, or (c) the suite/snapshot/authz-gate/build cannot be made green for a sub-unit — never commit a broken tree.

---

## Problem Frame

The full-app refactor plan defined five god-file splits as single units. Each is a behavior-preserving decomposition of one very large file:

| Origin unit | Target | Current size |
|---|---|---|
| U15 | `backend/api/admin_routes.py` -> `admin/` package | 2614 lines |
| U16 | `gnomad_local.py`, `db/models.py`, `multi_source_categorizer.py`, `scoring_engine.py`, `variant_routes.py` + rename `insights_service.py` | 5 files + rename |
| U18 | `frontend/src/components/admin/AdminPanel.tsx` -> per-tab | 3631 lines |
| U19 | `VariantDetailDialog.tsx` (2346) + `VariantSearch.tsx` (1842) + `categories/shared.tsx` (1278) | 3 files |
| U20 | `SettingsPanel.tsx` (944) + `dashboard/DashboardOverview.tsx` (912) | 2 files |

Attempting a whole-file split in one worker run reads the entire file, designs the full module layout, writes every new module, and verifies — which exceeds a single subagent's budget for the 2000+ line files (observed 3× in execution). **The fix is granularity, not approach:** one cohesive slice (≈1–3 target modules) per sub-unit, each independently committable on a green tree, with re-export shims preserving the public import surface so consumers never change.

---

## Key Technical Decisions

- **KTD1 — One slice per sub-unit, re-export shim preserves the surface.** Each sub-unit extracts a bounded set of symbols into new module(s) and leaves a re-export at the original import path (package `__init__` re-export, or a thin shim module) so every existing `from X import Y` keeps resolving. Consumers are never edited in the same sub-unit as a move — that keeps each unit small and the blast radius zero.
- **KTD2 — Package conversion is scaffold-first.** For a module that becomes a package (`admin/`, `gnomad/`, `db/models/`, `categorizer/`, `scoring/`, `variant/`), the first sub-unit creates the package skeleton + aggregating `__init__` (re-exporting the still-in-place original) and moves ONE slice as the proof-of-pattern; later sub-units move the remaining slices one batch at a time. The suite stays green after every sub-unit.
- **KTD3 — Admin guard at the aggregated router.** The `admin/` package applies `require_admin` once at the aggregated `APIRouter(dependencies=[Depends(require_admin)])`, so no per-domain sub-router can silently drop the guard. The negative-authz gate (`test_admin_route_authz.py`) runs after every Phase-A sub-unit as the regression proof.
- **KTD4 — `db/models` re-exports everything.** `db/models.py` has the widest import surface in the codebase. Its package `__init__` must re-export every public name (models, enums, `Base`) so no consumer import breaks. This is the highest-risk backend split; it gets its own sub-unit.
- **KTD5 — Frontend keeps exported names stable.** Component/hook/util names stay identical after extraction so category panels and other consumers need no churn. Verification is `pnpm build` + `pnpm lint` + per-surface code review (no test harness).
- **KTD6 — Pure move only.** No logic changes in any split sub-unit. If a move needs a behavior change to compile, that is a stop condition, not a silent edit.

---

## Planning Contract

### Assumptions

- The origin plan's per-file target module layouts (e.g. gnomAD -> cache/service/formatting/tx) are directional; the implementer may adjust module boundaries where the real code suggests a cleaner split, as long as each module stays under ~500 lines and the public surface is preserved.
- No external research is needed — this is a mechanical decomposition of already-understood code; the origin plan captured the design research.

### Sequencing

Backend first (test-guarded, lower risk), then frontend (build/lint-only), then docs.
- **Phase A** (admin package): U1 -> U2 -> U3 -> U4 (strictly serial — all touch `admin_routes.py` / `admin/__init__.py`).
- **Phase B** (other backend god-files): U5–U10 are largely independent files; run serially to keep the tree green and each commit isolated. U10 (rename) last.
- **Phase C** (frontend): U11 -> U12 -> U13 serial (all touch `AdminPanel.tsx`); U14 before U15 (shared.tsx feeds the dialog); U16/U17/U18 independent.
- **Phase D** (docs): U19 last (docs reflect final structure).

---

## Implementation Units

### Unit Index

| U-ID | Slice | Origin | Depends on |
|------|-------|--------|------------|
| U1 | admin/ scaffold + schemas + users | U15 | — (authz gate exists) |
| U2 | admin/ variant_mappings + discoveries | U15 | U1 |
| U3 | admin/ annotation_sources + jobs | U15 | U1 |
| U4 | admin/ etl + category_rules + retire admin_routes.py | U15 | U1, U2, U3 |
| U5 | split gnomad_local.py -> gnomad/ | U16 | — |
| U6 | split db/models.py -> db/models/ (re-export all) | U16 | — |
| U7 | split multi_source_categorizer.py -> categorizer/ | U16 | — |
| U8 | split scoring_engine.py -> scoring/ | U16 | — |
| U9 | split variant_routes.py -> variant/ | U16 | — |
| U10 | rename insights_service.py -> ai_insights_service.py | U16 | — |
| U11 | AdminPanel.tsx: extract constants + polling hooks | U18 | — |
| U12 | AdminPanel.tsx: extract users/registry/discoveries tabs | U18 | U11 |
| U13 | AdminPanel.tsx: extract remaining tabs + tab-shell | U18 | U11, U12 |
| U14 | categories/shared.tsx -> shared/ | U19 | — |
| U15 | VariantDetailDialog.tsx -> dialog package | U19 | U14 |
| U16 | VariantSearch.tsx -> search package | U19 | — |
| U17 | SettingsPanel.tsx -> section components | U20 | — |
| U18 | DashboardOverview.tsx -> section components | U20 | — |
| U19 | reconcile stale docs + migration convention | U22 | all |

---

### U1. admin/ scaffold + schemas + users

- **Goal:** Create the `backend/api/admin/` package with the aggregated guarded router, move the shared Pydantic models/helpers and the user-management handlers, and mount at the same prefix.
- **Origin:** U15. **Dependencies:** none (authz gate `test_admin_route_authz.py` already exists).
- **Files:** `backend/api/admin/__init__.py` (new — aggregator `APIRouter(dependencies=[Depends(require_admin)])`), `backend/api/admin/schemas.py` (new — Pydantic models + shared helpers/constants: `_is_source_stale`, `_source_cache_file_size`, `LATENCY_P95_THRESHOLD_SECONDS`, `SOURCE_TO_COLUMN` usage), `backend/api/admin/users.py` (new — user-management handlers), `backend/api/admin_routes.py` (remove moved code), `backend/main.py` (mount aggregated router at the same prefix).
- **Approach:** Scaffold the package (KTD2). Aggregated router applies `require_admin` once (KTD3). Move only the shared schemas/helpers and the `users` domain handlers; the rest stay in `admin_routes.py` and are included into the aggregated router for now (or `admin_routes.py`'s remaining router is mounted alongside) so the API surface is intact after this unit. Preserve every route path + method exactly.
- **Execution note:** Not purely behavior-preserving at the guard layer — run the negative-authz gate before and after.
- **Test scenarios:** Covers the authz gate. `test_admin_route_authz.py` green after (every admin path still 401/403 without admin). Existing admin tests unchanged. `Test expectation: no new tests` — structural move; the gate + existing admin suite are the proof.
- **Verification:** Authz gate green; suite 1777 green; `git`-diff of route (method, path) set identical before/after; main.py mounts at the same prefix.

### U2. admin/ variant_mappings + discoveries

- **Goal:** Move the variant-mappings and discoveries handlers into their own modules.
- **Origin:** U15. **Dependencies:** U1.
- **Files:** `backend/api/admin/variant_mappings.py` (new), `backend/api/admin/discoveries.py` (new), `backend/api/admin_routes.py` (remove moved), `backend/api/admin/__init__.py` (include the new sub-routers).
- **Approach:** Pure move of the two domains' handlers into modules included by the aggregated guarded router. Shared schemas come from `admin/schemas.py`.
- **Verification:** Authz gate green; suite 1777 green; route set identical.

### U3. admin/ annotation_sources + jobs

- **Goal:** Move the annotation-sources (incl. the cache-health endpoint) and jobs (incl. `/jobs/latency`) handlers into their own modules.
- **Origin:** U15. **Dependencies:** U1.
- **Files:** `backend/api/admin/annotation_sources.py` (new), `backend/api/admin/jobs.py` (new), `backend/api/admin_routes.py` (remove moved), `backend/api/admin/__init__.py` (include).
- **Approach:** Pure move. Carry the retrigger clobber guard and the found-rate/stale-flag health logic intact (they live in these domains).
- **Verification:** Authz gate green; suite 1777 green; route set identical.

### U4. admin/ etl + category_rules + retire admin_routes.py

- **Goal:** Move the remaining ETL and category-rules handlers, then retire `admin_routes.py` (delete, or reduce to a thin re-export if anything still imports it).
- **Origin:** U15. **Dependencies:** U1, U2, U3.
- **Files:** `backend/api/admin/etl.py` (new), `backend/api/admin/category_rules.py` (new), `backend/api/admin_routes.py` (delete or thin shim), `backend/api/admin/__init__.py` (include), `backend/tests/test_admin_route_authz.py` (update the router import if the router symbol moved).
- **Approach:** Move the last two domains. Grep for every importer of `admin_routes` (tests, main.py) and repoint to `admin`; if any external import must remain, leave a one-line re-export shim. No file over ~500 lines.
- **Verification:** Authz gate green (import updated); suite 1777 green; route set identical; no admin file over ~500 lines.

### U5. Split gnomad_local.py -> gnomad/

- **Goal:** Break `gnomad_local.py` into a `gnomad/` package (cache / service / formatting / tx) with a re-export `__init__`.
- **Origin:** U16. **Dependencies:** none.
- **Files:** `backend/services/gnomad/` (`cache.py`, `service.py`, `formatting.py`, `tx.py`, `__init__.py`), `backend/services/gnomad_local.py` (delete or thin re-export shim).
- **Approach:** Pure move along concern boundaries; `__init__` re-exports every name currently imported from `gnomad_local` (grep importers first, incl. `_SQLITE_FILE` used by admin cache-health). Watch relative-import dot shift (module -> package).
- **Execution note:** Pure move; snapshot + suite stay green.
- **Test scenarios:** `Test expectation: none -- behavior-preserving.` Existing gnomad tests + snapshot must pass unchanged.
- **Verification:** Suite 1777 + snapshot green; import surface intact; no module over ~500 lines.

### U6. Split db/models.py -> db/models/ (re-export everything)

- **Goal:** Break `db/models.py` into a `db/models/` package (user / analysis / dashboard_traits / annotations / reference_data) with an `__init__` re-exporting EVERY public name.
- **Origin:** U16. **Dependencies:** none. **Highest-risk backend split (KTD4).**
- **Files:** `backend/db/models/` (`user.py`, `analysis.py`, `dashboard_traits.py`, `annotations.py`, `reference_data.py`, `__init__.py`), `backend/db/models.py` (delete).
- **Approach:** All models share one `Base` — keep a single declarative `Base` in the package (e.g. in `__init__` or a `base.py`) imported by every submodule so relationships resolve by class name across modules. Re-export every model, enum, and `Base` from `__init__` (widest import surface). Preserve `passive_deletes`/cascade decls and the FK `ondelete=CASCADE` chain exactly. Alembic imports models from here — verify `alembic` still resolves metadata.
- **Execution note:** Pure move; verify SQLAlchemy relationship resolution (cross-module class-name refs) and that alembic autogenerate/metadata still loads.
- **Test scenarios:** `Test expectation: none -- behavior-preserving.` Full suite + snapshot + account-deletion cascade tests unchanged; confirm `alembic heads` still resolves.
- **Verification:** Suite 1777 + snapshot green; every prior `from ...db.models import X` resolves; `alembic heads` works; no module over ~500 lines.

### U7. Split multi_source_categorizer.py -> categorizer/

- **Goal:** Break the categorizer into `categorizer/` (models / evidence / scoring / engine) with a re-export `__init__`.
- **Origin:** U16. **Dependencies:** none.
- **Files:** `backend/services/categorizer/` (`models.py`, `evidence.py`, `scoring.py`, `engine.py`, `__init__.py`), `backend/services/multi_source_categorizer.py` (delete or thin shim). Note: `GENE_CATEGORY_MAP` is the single source imported by `variant_routes` (per completed U13) — keep it re-exported from the same path.
- **Approach:** Pure move; re-export the full surface incl. `GENE_CATEGORY_MAP`.
- **Test scenarios:** `Test expectation: none.` `test_multi_source_categorizer` + `test_auto_categorizer_helpers` unchanged.
- **Verification:** Suite green; import surface intact; no module over ~500 lines.

### U8. Split scoring_engine.py -> scoring/

- **Goal:** Break `scoring_engine.py` into `scoring/` (models / source_scorers / engine) with a re-export `__init__`.
- **Origin:** U16. **Dependencies:** none.
- **Files:** `backend/services/scoring/` (`models.py`, `source_scorers.py`, `engine.py`, `__init__.py`), `backend/services/scoring_engine.py` (delete or thin shim).
- **Approach:** Pure move; keep `_score_gnomad` and the other source scorers behavior-identical (they are snapshot-covered).
- **Test scenarios:** `Test expectation: none.` `test_scoring_engine` + snapshot unchanged.
- **Verification:** Suite 1777 + snapshot green; import surface intact; no module over ~500 lines.

### U9. Split variant_routes.py -> variant/

- **Goal:** Break `variant_routes.py` into a `variant/` package (lookup / search / helpers) with a re-export `__init__` (router symbol preserved).
- **Origin:** U16. **Dependencies:** none.
- **Files:** `backend/api/variant/` (`lookup.py`, `search.py`, `helpers.py`, `__init__.py`), `backend/api/variant_routes.py` (delete or thin shim), `backend/main.py` (repoint router import if the symbol moved).
- **Approach:** Pure move; preserve every route path + method and the `request`/`payload` param names (rate-limited endpoints). Aggregate the router in `__init__` and mount at the same prefix.
- **Test scenarios:** `Test expectation: none.` `test_variant_routes_extra` unchanged; route (method, path) set identical.
- **Verification:** Suite 1777 green; route set identical; no module over ~500 lines.

### U10. Rename insights_service.py -> ai_insights_service.py

- **Goal:** Rename the LLM insights service to its intended name and update imports.
- **Origin:** U16. **Dependencies:** none.
- **Files:** `backend/services/ai_insights_service.py` (renamed from `insights_service.py`), `backend/api/insights_routes.py` + any other importer (update imports), tests referencing the old module path.
- **Approach:** Reference-aware rename (grep/`find_referencing_symbols` every importer). Pure rename — no logic change.
- **Test scenarios:** `Test expectation: none.` Suite unchanged; `grep insights_service` returns only the new name (+ unrelated `insight` words).
- **Verification:** Suite 1777 green; old module name gone; imports updated.

### U11. AdminPanel.tsx: extract constants + polling hooks

- **Goal:** Extract the label/config maps and the ETL/job polling logic out of `AdminPanel.tsx` into `constants.ts` + hooks — the foundation for the per-tab split.
- **Origin:** U18. **Dependencies:** none. **No test harness — build/lint + review only.**
- **Files:** `frontend/src/components/admin/constants.ts` (new), `frontend/src/components/admin/useAdminJobs.ts` (new), `frontend/src/components/admin/useEtlProgress.ts` (new), `frontend/src/components/admin/AdminPanel.tsx` (consume the extracts). Note: `useAdminJobs`/`useEtlProgress` use the existing `apiFetch`/`authFetch` client from release-U9.
- **Approach:** Move constants + polling state/effects verbatim into the hooks; `AdminPanel` calls the hooks. No behavior change.
- **Test scenarios:** `Test expectation: none (no FE harness).` Verify `pnpm build` + `pnpm lint` (0 errors) + code review that polling still fires on the same triggers.
- **Verification:** Build + lint clean (0 errors); AdminPanel line count drops; hooks own the polling.

### U12. AdminPanel.tsx: extract users/registry/discoveries tabs

- **Goal:** Extract the first three tab bodies into components.
- **Origin:** U18. **Dependencies:** U11.
- **Files:** `frontend/src/components/admin/AdminUsersTab.tsx`, `AdminRegistryTab.tsx`, `AdminDiscoveriesTab.tsx` (new), `AdminPanel.tsx` (render the components).
- **Approach:** One component per `VALID_TABS` entry; pass state/handlers as props or via the U11 hooks. Verbatim JSX move.
- **Test scenarios:** `Test expectation: none.` Build + lint + code review that each tab renders + acts identically.
- **Verification:** Build + lint clean; three tabs render from their own files.

### U13. AdminPanel.tsx: extract remaining tabs + tab-shell

- **Goal:** Extract the last four tab bodies and reduce `AdminPanel.tsx` to a tab-shell composition.
- **Origin:** U18. **Dependencies:** U11, U12.
- **Files:** `frontend/src/components/admin/AdminDataSourcesTab.tsx`, `AdminRulesTab.tsx`, `AdminAnnotationsTab.tsx`, `AdminJobsTab.tsx` (new), `AdminPanel.tsx` (tab-shell only).
- **Approach:** Verbatim move of the remaining tab JSX; `AdminPanel` becomes tab selection + composition. Carry the data-sources health rendering (release-U13) intact.
- **Test scenarios:** `Test expectation: none.` Build + lint + per-tab code review.
- **Verification:** Build + lint clean; no admin component over ~500 lines; all 7 tabs render.

### U14. categories/shared.tsx -> shared/

- **Goal:** Break the 1278-line `shared.tsx` grab-bag into concern modules, keeping exported names stable.
- **Origin:** U19. **Dependencies:** none.
- **Files:** `frontend/src/components/categories/shared/` (`theme-classes.ts`, `severity.ts`, `badges.tsx`, `bars.tsx`, `boxes.tsx`, `grouping.ts`, `format.ts`, `index.ts` re-exporting all), `frontend/src/components/categories/shared.tsx` (delete or thin re-export). Note: `useThemeClasses` already delegates to `utils/theme.ts` (release-U10) — preserve that.
- **Approach:** Split by concern; `index.ts` (or a kept `shared.tsx` shim) re-exports every name so the ~13 category panels need no import churn.
- **Test scenarios:** `Test expectation: none.` Build + lint; grep confirms category-panel imports still resolve.
- **Verification:** Build + lint clean; exported names stable; no module over ~500 lines.

### U15. VariantDetailDialog.tsx -> dialog package

- **Goal:** Break the 2346-line dialog into one Section component per annotation source + shared types/format helpers.
- **Origin:** U19. **Dependencies:** U14 (shared helpers land first).
- **Files:** `frontend/src/components/categories/VariantDetailDialog/` (one `*Section.tsx` per annotation source, `variant-types.ts`, `format.ts`, `index.tsx` composing them), old `VariantDetailDialog.tsx` (delete or thin re-export).
- **Approach:** One section component per source; the dialog composes them. Keep the `details.publications` LitVar rendering (release-U10) + the gnomAD AF gating (release-U4) intact. Verbatim JSX move.
- **Test scenarios:** `Test expectation: none.` Build + lint + code review: open a variant dialog, each annotation section still renders.
- **Verification:** Build + lint clean; no component over ~500 lines; dialog behaves identically.

### U16. VariantSearch.tsx -> search package

- **Goal:** Split the 1842-line search into its two tabs plus a data hook.
- **Origin:** U19. **Dependencies:** none.
- **Files:** `frontend/src/components/VariantSearch/` (`MyVariantsTab.tsx`, `VariantLookupTab.tsx`, `lookup-types.ts`, `useVariantSearch.ts`, `index.tsx`), old `VariantSearch.tsx` (delete or thin re-export).
- **Approach:** Extract the data-fetching into `useVariantSearch` (uses `apiFetch`), split the two tabs, compose in `index.tsx`. Keep the gnomAD frequency-card gating (release-U4) intact.
- **Test scenarios:** `Test expectation: none.` Build + lint + code review: run a lookup and a my-variants view.
- **Verification:** Build + lint clean; no component over ~500 lines.

### U17. SettingsPanel.tsx -> section components

- **Goal:** Break the 944-line settings into per-section components.
- **Origin:** U20. **Dependencies:** none.
- **Files:** `frontend/src/components/SettingsPanel/` (`ProfileSection.tsx`, `PasswordSection.tsx`, `NotificationsSection.tsx`, `SharingSection.tsx`, `SavedVariantsSection.tsx`, `index.tsx`), old `SettingsPanel.tsx` (delete or thin re-export).
- **Approach:** Section-per-concern. Reuse the existing `useFeedback`/`useDarkMode` hooks (release-U11) — do not reintroduce local feedback state. Keep the `apiFetch` calls + the printable-report disclaimer (release-U8) intact.
- **Test scenarios:** `Test expectation: none.` Build + lint + code review: change password, toggle notifications, share dashboard.
- **Verification:** Build + lint clean; no section over ~500 lines.

### U18. DashboardOverview.tsx -> section components

- **Goal:** Extract the named sub-blocks of the 912-line overview into components.
- **Origin:** U20. **Dependencies:** none.
- **Files:** `frontend/src/components/dashboard/CategoryHighlights.tsx`, `OverviewCharts.tsx`, `HealthInsights.tsx` (new), `DashboardOverview.tsx` (compose).
- **Approach:** Verbatim extraction of the already-named sub-blocks; overview composes them.
- **Test scenarios:** `Test expectation: none.` Build + lint + code review: overview renders with charts + highlights.
- **Verification:** Build + lint clean; no component over ~500 lines.

### U19. Reconcile stale docs + migration convention

- **Goal:** Bring docs in line with the refactored structure and document the migration-naming convention.
- **Origin:** U22. **Dependencies:** all prior units (docs reflect final state).
- **Files:** `.github/copilot-instructions.md` (`variant_registry` -> `variant_mappings`), `docs/architecture.md` (single annotation path, split packages, cookie auth), `docs/data_sources_schema.md` (gnomAD conservation-only note), `README.md` (if structure changed), plus commit the pending uncommitted meta/doc changes.
- **Approach:** Update prose to match code; document the sequential `NNN_` migration convention (do not rewrite applied migration history). Grep for stale references (`variant_registry`, `OptimizedGeneticAPIService` dual-name, Bearer-token claims) and fix.
- **Test scenarios:** `Test expectation: none -- docs.` Grep for stale refs returns nothing; referenced paths exist post-refactor.
- **Verification:** Docs match code; no stale references; migration convention documented.

---

## Verification Contract

| Gate | Command | Applies |
|------|---------|---------|
| Backend suite | `uv run pytest backend/tests/ -q` | U1–U10; must stay green (baseline 1777) |
| Characterization snapshot | `uv run pytest backend/tests/test_insight_snapshot.py -q` | U5, U6, U7, U8 (no insight drift) |
| Admin negative-authz gate | `uv run pytest backend/tests/test_admin_route_authz.py -q` | U1–U4 (before + after each) |
| Frontend build | `cd frontend && pnpm build` | U11–U18 |
| Frontend lint | `cd frontend && pnpm lint` | U11–U18 (keep 0 errors) |
| Route-set parity | enumerate (method, path) before/after | U1–U4, U9 |

Behavioral checks tests won't prove (frontend has no harness) — per-surface manual/code review is the named replacement verification for U11–U18.

---

## Definition of Done

- Every god-file split landed as its own commit(s) on a green tree; no unit left the suite/snapshot/authz-gate/build red.
- `admin_routes.py`, `gnomad_local.py`, `db/models.py`, `multi_source_categorizer.py`, `scoring_engine.py`, `variant_routes.py` replaced by packages (or retired to thin shims); `insights_service.py` renamed.
- `AdminPanel.tsx`, `VariantDetailDialog.tsx`, `VariantSearch.tsx`, `categories/shared.tsx`, `SettingsPanel.tsx`, `DashboardOverview.tsx` split into per-concern modules; no split module over ~500 lines.
- Public import surfaces preserved (re-export shims where wide); consumers unchanged.
- Backend suite green at ≥1777; snapshot green; authz gate green; frontend build + lint (0 errors).
- Docs reconciled (U19); pending meta committed.

---

## Scope Boundaries

### In scope
The five deferred god-file splits (origin U15/U16/U18/U19/U20), re-decomposed into subagent-sized sub-units, and the docs reconcile (origin U22).

### Deferred to Follow-Up Work
- **gnomAD re-ETL / GRCh37-38 build fix (origin U7 tail):** a data/ops task requiring the raw `data_sources/` files + prod DB; the collapse-and-document half already shipped (release-U4).
- **`shared_variant_annotations` bloat strategy (origin U8):** needs prod-data column-size measurement before choosing prune-vs-compress; not a code-only split.

### Outside this refactor's identity
No behavior changes, no new features, no product-scope changes — pure structural moves.

---

## Risks & Dependencies

- **`db/models.py` split (U6)** is the widest-surface, highest-risk backend change — a missed re-export breaks many consumers and alembic. Mitigation: re-export everything from `__init__`, single shared `Base`, verify `alembic heads` + full suite.
- **Frontend splits (U11–U18)** have no test harness — a split that compiles but breaks runtime behavior won't be caught by tests. Mitigation: verbatim JSX moves, stable exported names, `pnpm build` + `pnpm lint` + per-surface code review; keep each unit small so review is tractable.
- **Admin split (U1–U4)** could drop an auth guard. Mitigation: guard at the aggregated router + the negative-authz gate before/after every unit.
- **Serial contention:** Phase A units and Phase C U11–U13 all touch one file each in sequence — must run serially, not parallel.
