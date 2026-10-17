#!/usr/bin/env bash
# One entry point for the AWS viva, regression checks and source handover.
set -euo pipefail
cd "$(dirname "$0")"

show_help() {
  cat <<'HELP'
Wonderland demonstration

  ./demo.sh up               Plan, create AWS, build and release (no extra prompt)
  ./demo.sh status           Show the current server state and website URLs
  ./demo.sh check            Check hosted APIs, access rules and Metabase SQL
  ./demo.sh monitor          Open the private Metabase tunnel
  ./demo.sh down             Plan, back up, destroy and audit (no extra prompt)
  ./demo.sh audit            Confirm no hosted demo resources remain

Preview only
  ./demo.sh plan             Show the deployment plan without applying
  ./demo.sh plan-down        Show the deletion plan without applying

Preparation (does not create AWS resources)
  ./demo.sh test             Run regression tests and build both websites
  ./demo.sh terraform-check  Validate Terraform and run offline mocked plans
  ./demo.sh package          Create a source-only ZIP without private files
  ./demo.sh local            Run the optional laptop demo

Advanced: ./cloud.sh --help
Guides: docs/demo.md, docs/viva.md, docs/code-guide.md
HELP
}

command="${1:-help}"
if [[ $# -gt 0 ]]; then shift; fi
case "$command" in
  help|-h|--help) show_help ;;
  check) exec ./cloud.sh verify "$@" ;;
  monitor) exec ./cloud.sh monitoring "$@" ;;
  audit) exec ./cloud.sh cleanup-check "$@" ;;
  up|down|status|plan|plan-down) exec ./cloud.sh "$command" "$@" ;;
  test|package) exec ./start.sh "$command" "$@" ;;
  local) exec ./start.sh start "$@" ;;
  terraform-check)
    if [[ ! -x .venv/bin/python ]]; then
      echo "Python setup is missing. Follow README.md."
      exit 1
    fi
    exec .venv/bin/python scripts/validate-cloud.py "$@"
    ;;
  *) echo "Unknown command: $command" >&2; show_help >&2; exit 2 ;;
esac
