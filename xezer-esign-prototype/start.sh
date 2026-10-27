#!/usr/bin/env bash
# One-command demo start (macOS / Linux): builds the frontend and serves everything on http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"

cd backend
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

cd ../frontend
[ -d node_modules ] || npm install
npm run build

cd ../backend
echo
echo "  Xezer e-İmza prototype → http://localhost:8000"
echo
exec uvicorn app.main:app --port 8000
