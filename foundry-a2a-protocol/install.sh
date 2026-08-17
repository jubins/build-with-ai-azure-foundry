#!/usr/bin/env bash
set -e

# Python 3.10+ required
python3 --version

# Create the venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo
echo "Dependencies installed."
echo "Next: cp .env.example .env  (then fill in your Foundry values)"

# Optional — only needed for the 'Deploy to Azure' section of the README.
# curl -fsSL https://aka.ms/install-azd.sh | bash
# azd extension install microsoft.foundry
