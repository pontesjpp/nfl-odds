#!/usr/bin/env bash
# ============================================================
# settle_and_push.sh
# Settle all pending bets using live ESPN stats, then commit
# and push the updated database so Render has the latest data.
#
# Usage:
#   ./scripts/settle_and_push.sh              # settle all portfolio types
#   ./scripts/settle_and_push.sh safe         # settle only 'safe'
#   ./scripts/settle_and_push.sh safe_flat    # settle only 'safe_flat'
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB_PATH="$PROJECT_ROOT/data/nfl_odds.db"

PORTFOLIO_TYPE="${1:-}"

echo "🏈 NFL Odds — Settle & Push"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Settle bets via the settle_portfolio function
echo "📡 Fetching live ESPN stats and settling bets..."
echo ""

SETTLE_SCRIPT=$(cat <<'PYEOF'
import sys, json

# Settle function accepts optional portfolio_type
from nfl_odds.dashboard.api import settle_portfolio

portfolio_type = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None

# Settle the main portfolio type (or all if none specified)
types_to_settle = [portfolio_type] if portfolio_type else ["safe", "safe_flat", "high_risk", "all_props"]

total_settled = 0
for ptype in types_to_settle:
    try:
        result = settle_portfolio(portfolio_type=ptype)
        settled = result.get("settled", 0)
        total_settled += settled
        icon = "✅" if settled > 0 else "⏸️"
        print(f"  {icon} {ptype:12s} → {result.get('message', 'done')}")
    except Exception as e:
        print(f"  ❌ {ptype:12s} → Error: {e}")

print()

# Quick summary
from nfl_odds.data.database import SessionLocal, Bet
db = SessionLocal()
for ptype in types_to_settle:
    bets = db.query(Bet).filter(Bet.portfolio_type == ptype).all()
    won = len([b for b in bets if b.result == "won"])
    lost = len([b for b in bets if b.result == "lost"])
    push = len([b for b in bets if b.result == "push"])
    pending = len([b for b in bets if b.result == "pending"])
    pnl = sum(b.profit_units for b in bets if b.result in ("won", "lost"))
    print(f"  📊 {ptype:12s}: {won}W/{lost}L/{push}P/{pending}Pend  P&L: {pnl:+.2f}u")
db.close()

print()
print(f"Total newly settled: {total_settled}")

# Exit with code 0 even if nothing settled (not an error)
PYEOF
)

cd "$PROJECT_ROOT"
PYTHONPATH=src .venv/bin/python -c "$SETTLE_SCRIPT" "$PORTFOLIO_TYPE"

echo ""

# 2. Check if DB actually changed
if git diff --quiet "$DB_PATH" 2>/dev/null; then
    echo "ℹ️  No changes to database. Nothing to commit."
    echo "   (All bets were already settled or no new games finished.)"
    exit 0
fi

# 3. Show what changed
echo "💾 Database updated. Changes detected:"
DB_SIZE=$(du -h "$DB_PATH" | cut -f1)
echo "   data/nfl_odds.db ($DB_SIZE)"
echo ""

# 4. Commit and push
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
COMMIT_MSG="chore: settle results ($TIMESTAMP)"

echo "📤 Committing and pushing to git..."
git add "$DB_PATH"
git commit -m "$COMMIT_MSG"
git push

echo ""
echo "✅ Done! Render will pick up the updated results on next deploy."
echo "   To force a Render redeploy, push any code change or use the Render dashboard."
