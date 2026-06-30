#!/usr/bin/env bash
set -e

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

uvicorn agent:app --reload --host 0.0.0.0 --port 8000
