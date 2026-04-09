#!/usr/bin/env bash
set -euo pipefail

SONAR_HOST="${SONAR_HOST_URL:-http://localhost:9000}"
SONAR_TOKEN="${SONAR_TOKEN:?Set SONAR_TOKEN before running (generate at $SONAR_HOST/account/security)}"

echo "Generating Python coverage report..."
PYENV_VERSION=system uv run pytest backend/tests/ -x -q \
  --cov=backend --cov-report=xml:coverage.xml 2>/dev/null || true

echo "Running SonarScanner..."
docker run --rm \
  --network=host \
  -e SONAR_HOST_URL="$SONAR_HOST" \
  -e SONAR_TOKEN="$SONAR_TOKEN" \
  -v "$(pwd):/usr/src" \
  sonarsource/sonar-scanner-cli:latest

echo "Done — results at $SONAR_HOST/dashboard?id=dna-toolkit"
