#!/usr/bin/env bash
# Encerra ambos os processos se você apertar Ctrl+C
trap 'kill 0' SIGINT SIGTERM EXIT

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "🚀 Iniciando Backend (FastAPI :8000) e Frontend (Next.js :3000)..."

uv run uvicorn nfl_odds.dashboard.api:app --reload --port 8000 &
npm run dev --prefix frontend &

wait
