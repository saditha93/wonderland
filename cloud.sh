#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
export PATH="$PWD/tmp/tools:$PATH"
exec .venv/bin/python scripts/simple_cloud.py "${@:-status}"
