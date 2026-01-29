#!/usr/bin/env bash
set -euo pipefail
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if [ "${1:-}" = "optional" ]; then
  pip install -r requirements-optional.txt
fi
if [ "${1:-}" = "dev" ]; then
  pip install -r requirements-dev.txt
fi
