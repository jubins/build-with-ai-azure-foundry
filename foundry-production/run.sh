#!/usr/bin/env bash
set -e

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

MODE="${1:-audit}"
shift || true

case "$MODE" in
  # The pre-launch checklist, as a pass/fail report.
  audit)
    exec python preflight_audit.py "$@"
    ;;

  # Show what the current env resolves to, and what each setting logs.
  config)
    exec python tracing_config.py "$@"
    ;;

  # Call the agent with a hard output-token cap. Needs Foundry credentials.
  guardrails)
    exec python agent_guardrails.py "$@"
    ;;

  # Deploy the five alert rules.
  alerts)
    exec ./deploy_alerts.sh "$@"
    ;;

  *)
    echo "Usage: ./run.sh [audit|config|guardrails|alerts] [args]"
    echo
    echo "  audit        Run the pre-launch checklist (default)"
    echo "  config       Show resolved tracing config and what it logs"
    echo "  guardrails   Call the agent with max_output_tokens set"
    echo "  alerts       Deploy the five Monitor alert rules"
    exit 1
    ;;
esac
