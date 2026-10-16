#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "Python setup is missing. Follow the one-time setup in README.md."
  exit 1
fi
exec .venv/bin/python scripts/local/cli.py "$@"
