#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m pytest -q
npm --prefix frontend run build
if command -v docker >/dev/null 2>&1; then
  POSTGRES_PASSWORD=validation-placeholder docker compose config --quiet
else
  echo "Docker Compose validation skipped: Docker is not installed."
fi
