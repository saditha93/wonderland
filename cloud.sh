#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
export PATH="$PWD/tmp/tools:$PATH"
# Preserve the selected local Docker engine when release uses private registry credentials.
if [[ -z "${DOCKER_HOST:-}" ]] && command -v docker >/dev/null 2>&1; then
  demo_docker_host="$(docker context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null || true)"
  if [[ -n "$demo_docker_host" ]]; then
    export DOCKER_HOST="$demo_docker_host"
  fi
fi
if [[ -x "$HOME/.docker/cli-plugins/docker-buildx" ]]; then
  mkdir -p secrets/simple-cloud/docker/cli-plugins
  ln -sf "$HOME/.docker/cli-plugins/docker-buildx" secrets/simple-cloud/docker/cli-plugins/docker-buildx
fi
exec .venv/bin/python scripts/simple_cloud.py "${@:-status}"
