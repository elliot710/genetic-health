#!/usr/bin/env bash
# deploy.sh — Pull latest code from GitHub and rebuild changed containers on the production server.
#
# Usage:
#   ./deploy.sh                          # rebuild backend + frontend (default)
#   ./deploy.sh --backend-only           # rebuild backend only
#   ./deploy.sh --frontend-only          # rebuild frontend only
#   ./deploy.sh --no-build               # pull + migrate only, skip rebuild
#
# Requirements (local machine):
#   - SSH access to the production server (root@204.168.200.44)
#   - The server must have its GitHub deploy key at ~/.ssh/github_deploy
#
# The script:
#   1. Pulls latest code on the server using the deploy key
#   2. Runs database migrations (alembic upgrade head)
#   3. Rebuilds and restarts the requested containers
#   4. Tails backend logs briefly to confirm startup

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────────
SERVER="root@204.168.200.44"
APP_DIR="/app"
BRANCH="dev"
BACKEND_CONTAINER="app-backend-1"
WORKER_CONTAINER="app-worker-1"

# ── Colour helpers ───────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}▶ $*${NC}"; }
success() { echo -e "${GREEN}✓ $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠ $*${NC}"; }
die()     { echo -e "${RED}✗ $*${NC}" >&2; exit 1; }

# ── Argument parsing ─────────────────────────────────────────────────────────
BUILD_BACKEND=true
BUILD_FRONTEND=true
BUILD_WORKER=true
SKIP_BUILD=false

for arg in "$@"; do
  case "$arg" in
    --backend-only)  BUILD_FRONTEND=false; BUILD_WORKER=false ;;
    --frontend-only) BUILD_BACKEND=false;  BUILD_WORKER=false ;;
    --no-build)      SKIP_BUILD=true ;;
    --help|-h)
      sed -n '2,20p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) die "Unknown option: $arg  (use --help for usage)" ;;
  esac
done

# ── Pre-flight: check SSH reachability ───────────────────────────────────────
info "Checking SSH connectivity to $SERVER …"
ssh -o ConnectTimeout=8 -o BatchMode=yes "$SERVER" "echo ok" > /dev/null \
  || die "Cannot reach $SERVER. Check your SSH keys / VPN."
success "Server reachable"

# ── Remote work ──────────────────────────────────────────────────────────────
info "Pulling latest code on server (branch: $BRANCH) …"
ssh "$SERVER" bash -s -- "$APP_DIR" "$BRANCH" <<'REMOTE'
set -euo pipefail
APP_DIR="$1"
BRANCH="$2"
cd "$APP_DIR"

# ── Protect .env ──────────────────────────────────────────────────────────────
# The canonical production .env lives at /root/.env.epigenic (outside the git repo).
# We back up /app/.env there before any git operation and restore it after.
ENV_BACKUP="/root/.env.epigenic"
if [[ -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env" "$ENV_BACKUP"
fi

# Use the GitHub deploy key for this git operation
export GIT_SSH_COMMAND="ssh -i /root/.ssh/github_deploy -o StrictHostKeyChecking=accept-new"

# Stash any uncommitted local changes (e.g. manual hotfixes scp'd to server)
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "  Stashing local changes …"
  git stash push -m "pre-deploy stash $(date +%Y%m%d-%H%M%S)"
fi

git fetch origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

# ── Restore .env ──────────────────────────────────────────────────────────────
if [[ -f "$ENV_BACKUP" ]]; then
  cp "$ENV_BACKUP" "$APP_DIR/.env"
  echo "  .env restored from $ENV_BACKUP"
else
  echo "  WARNING: no .env backup found at $ENV_BACKUP — create one manually!"
fi

echo "  HEAD: $(git log -1 --oneline)"
REMOTE
success "Code updated"

# ── Migrations ───────────────────────────────────────────────────────────────
info "Running database migrations …"
ssh "$SERVER" bash -s -- "$APP_DIR" "$BACKEND_CONTAINER" <<'REMOTE'
set -euo pipefail
APP_DIR="$1"
CONTAINER="$2"
cd "$APP_DIR"
# Container may still be starting after a prior build — wait briefly
for i in 1 2 3 4 5; do
  STATUS=$(docker inspect --format '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "absent")
  [[ "$STATUS" == "running" ]] && break
  echo "  Waiting for $CONTAINER to be running (attempt $i/5) …"
  sleep 4
done
docker exec "$CONTAINER" uv run alembic upgrade head
echo "  Migration version: $(docker exec "$CONTAINER" uv run alembic current 2>&1 | grep '(' | head -1)"
REMOTE
success "Migrations applied"

# ── Rebuild containers ───────────────────────────────────────────────────────
if [[ "$SKIP_BUILD" == true ]]; then
  warn "Skipping container rebuild (--no-build)"
else
  if [[ "$BUILD_BACKEND" == true ]]; then
    info "Rebuilding backend + worker …"
    ssh "$SERVER" bash -s -- "$APP_DIR" <<'REMOTE'
set -euo pipefail
cd "$1"
docker compose up -d --build backend worker 2>&1 | grep -E 'Built|Started|Recreated|error' || true
REMOTE
    success "Backend + worker rebuilt"
  fi

  if [[ "$BUILD_FRONTEND" == true ]]; then
    info "Rebuilding frontend …"
    ssh "$SERVER" bash -s -- "$APP_DIR" <<'REMOTE'
set -euo pipefail
cd "$1"
docker compose up -d --build frontend 2>&1 | grep -E 'Built|Started|Recreated|error' || true
REMOTE
    success "Frontend rebuilt"
  fi
fi

# ── Health check ─────────────────────────────────────────────────────────────
info "Waiting for backend to report healthy …"
ssh "$SERVER" bash -s -- "$BACKEND_CONTAINER" <<'REMOTE'
set -euo pipefail
CONTAINER="$1"
for i in $(seq 1 20); do
  STATUS=$(docker inspect --format '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "absent")
  HEALTH=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CONTAINER" 2>/dev/null || echo "unknown")
  if [[ "$STATUS" == "running" && ( "$HEALTH" == "healthy" || "$HEALTH" == "none" ) ]]; then
    echo "  $CONTAINER is $STATUS (health: $HEALTH)"
    docker logs "$CONTAINER" --since=60s 2>&1 | grep -E 'Application startup complete|Uvicorn running|ERROR' | tail -3
    exit 0
  fi
  echo "  Waiting ($i/20) — status: $STATUS, health: $HEALTH"
  sleep 3
done
echo "WARNING: backend did not reach healthy state within 60s"
REMOTE

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
success "Deploy complete!"
echo -e "  Frontend : ${CYAN}https://epigenic.xyz${NC}"
echo -e "  API docs : ${CYAN}https://api.epigenic.xyz/docs${NC}"
