#!/bin/sh
set -e
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cd web && npm install
echo "Ready. API: uvicorn api.main:app --reload | Web: cd web && npm run dev"
