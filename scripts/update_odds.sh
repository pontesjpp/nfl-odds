#!/usr/bin/env bash
# ============================================================
# update_odds.sh
# Fluxo completo para quando novas apostas forem aparecendo:
# 1. Raspa as novas linhas e odds do Betclic (Playwright)
# 2. Roda a pipeline de IA/XGBoost para calcular EV e valor
# 3. Faz commit e push dos novos dados para o Render/Vercel
#
# Uso:
#   ./scripts/update_odds.sh              # Semana 2 (modo padrão lento e seguro)
#   ./scripts/update_odds.sh 2            # Semana específica
#   ./scripts/update_odds.sh 2 --fast     # Modo rápido (5-10s por jogo)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

WEEK="${1:-2}"
FAST_FLAG=""

if [[ "${2:-}" == "--fast" ]] || [[ "${1:-}" == "--fast" ]]; then
    FAST_FLAG="--fast"
    if [[ "$WEEK" == "--fast" ]]; then
        WEEK=2
    fi
fi

echo "🏈 NFL Odds — Atualizar Novas Apostas (Semana $WEEK)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Executar o Scraper
echo "🕷️  [1/3] Raspando novas linhas no Betclic..."
if [ -n "$FAST_FLAG" ]; then
    PYTHONPATH=src .venv/bin/python scripts/run_scraper.py --fast
else
    PYTHONPATH=src .venv/bin/python scripts/run_scraper.py
fi
echo ""

# 2. Executar a Pipeline de IA
echo "🧠 [2/3] Calculando probabilidades XGBoost e apostas de valor (+EV)..."
uv run python pipeline.py --live --week "$WEEK"
echo ""

# 3. Verificar se houve novos dados gerados
echo "💾 [3/3] Verificando dados gerados..."
if git diff --quiet data/live_value_bets.parquet data/betclic_parsed_odds.parquet 2>/dev/null; then
    echo "ℹ️  Nenhuma aposta nova encontrada em relação ao último envio."
    echo "   (As linhas no Betclic ainda não mudaram ou já estavam sincronizadas)."
    exit 0
fi

# 4. Commit e push para atualizar Render e Vercel
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
COMMIT_MSG="chore: update live odds week $WEEK ($TIMESTAMP)"

echo "📤 Subindo novas oportunidades para o GitHub..."
git add data/live_value_bets.parquet data/betclic_parsed_odds.parquet data/live_features.parquet data/*_cache.json 2>/dev/null || true
git commit -m "$COMMIT_MSG"
git push origin master

echo ""
echo "✅ Pronto! As novas apostas foram enviadas."
echo "   O Render atualizará o backend em ~1-2 minutos."
echo "   Depois, basta abrir a Vercel e importar na Carteira!"
