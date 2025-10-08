#!/usr/bin/env bash
set -euo pipefail

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install

if [ ! -f .env ] && [ -f env.example ]; then
  cp env.example .env
fi

echo "[ok] Environment ready. Activate with 'source .venv/bin/activate'."
