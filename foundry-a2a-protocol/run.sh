#!/usr/bin/env bash
set -e

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

MODE="${1:-demo}"
shift || true

case "$MODE" in
  # The specialist A2A server on its own.
  specialist)
    exec python a2a_server.py
    ;;

  # Hand-rolled A2A round trip against a running specialist.
  client)
    exec python a2a_client.py "$@"
    ;;

  # Local coordinator → A2A → specialist. Starts the specialist itself,
  # so this is the one-command version of the demo.
  demo)
    PORT="${A2A_PORT:-8001}"

    if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
      echo "Using specialist already running on port ${PORT}."
      exec python run_demo.py "$@"
    fi

    echo "Starting specialist on port ${PORT}..."
    python a2a_server.py &
    SPECIALIST_PID=$!
    trap 'kill $SPECIALIST_PID 2>/dev/null || true' EXIT

    # Wait for the agent card to come up
    for _ in $(seq 1 30); do
      if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
        break
      fi
      sleep 0.5
    done

    python run_demo.py "$@"
    ;;

  # Create/update the Foundry coordinator agent with the A2A tool attached.
  coordinator)
    exec python coordinator.py "$@"
    ;;

  *)
    echo "Usage: ./run.sh [demo|specialist|client|coordinator] [args]"
    echo
    echo "  demo         Local coordinator → A2A → specialist (default)"
    echo "  specialist   Run the A2A specialist server only"
    echo "  client       Manual A2A round trip against a running specialist"
    echo "  coordinator  Create/update the Foundry coordinator agent"
    exit 1
    ;;
esac
