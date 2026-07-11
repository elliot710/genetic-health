# Runbook: Reclaim Docker cruft on production

Reclaim disk consumed by dangling Docker images and build cache (~117 GB per the
data-sources consumption audit, P1). This is a **manual operator step run over
SSH on the production host**. No automated pipeline performs any action in this
runbook.

## Scope

**In scope:** dangling/unused Docker images and Docker build cache.

**NEVER touch:**
- PostgreSQL data (the 61 GB database and its large ETL tables are live).
- `data_sources/` raw annotation files (large, gitignored, actively read by the worker).
- Named volumes backing the database or persisted app state.
- Any image currently used by a running container.

If a command in this runbook would remove one of the above, stop.

## Preconditions

- You are on the production host (SSH), with permission to run `docker`.
- A recent database backup exists (this runbook does not touch the DB, but never
  run host maintenance without one).
- Off-peak window; a `docker builder prune` can briefly increase IO.

## 1. Measure before

```bash
docker system df                 # summary: images / containers / volumes / build cache
docker system df -v | head -50   # per-item detail
df -h /                          # host disk headroom
```

Record the reclaimable numbers so the after-measurement can confirm the win.

## 2. Confirm what is active (do not skip)

```bash
# Images referenced by running containers — these must survive.
docker ps --format '{{.Image}}' | sort -u

# All images, newest first, to eyeball what is in use vs stale.
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}'
```

Verify the current app/db images (the ones `docker compose` is running) appear in
the running set. Only images NOT in that set are candidates for removal.

## 3. Prune build cache first (safest, usually the biggest win)

```bash
docker builder prune            # removes unused build cache; prompts for confirmation
```

Answer `y` only after reading the reclaimable figure it prints.

## 4. Prune unused images

```bash
# Conservative: dangling (untagged) layers only.
docker image prune

# Aggressive: every image not used by a running container.
# Re-confirm step 2 first — a stopped-but-needed container's image is removable here.
docker image prune -a
```

Prefer `docker image prune` (dangling only) unless step 2 confirmed the tagged
images you would drop are genuinely stale. `docker image prune -a` removes the
image of any container that is not currently running.

## 5. Do NOT run these

```bash
docker system prune --volumes   # would target volumes → can delete DB/persisted data
docker volume prune             # same risk
```

Volume pruning is explicitly out of scope; the database and persisted state live
in volumes.

## 6. Measure after

```bash
docker system df
df -h /
```

Confirm the reclaimed space matches step 1's reclaimable estimate and that the
app + database containers are still `Up`:

```bash
docker compose ps
```

## Convenience target (optional)

`make reclaim-docker-cruft` runs the read-only verify steps (2 + 6) so an operator
can review before pruning. It intentionally does **not** prune — the destructive
`prune` commands stay manual, run by hand after reviewing the output.
