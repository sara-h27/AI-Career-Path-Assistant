#!/usr/bin/env bash
# One command: creates .venv on first run, installs requirements, starts the app.
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
[[ -f .env ]] || cp .env.example .env
exec .venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000
