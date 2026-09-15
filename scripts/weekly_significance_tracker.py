#!/usr/bin/env python3
"""
weekly_significance_tracker.py — Statistical Significance Tracker

Runs weekly to accumulate subgroup data and test whether observed patterns
are statistically significant or just sample noise.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/weekly_significance_tracker.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from collections import defaultdict
from scipy import stats
import numpy as np
from nfl_odds.data.database import SessionLocal, Bet


def binomial_test(wins: int, total: int, p0: float) -> dict:
    """Two-sided binomial exact test against null hypothesis p0."""
    if total == 0:
        return {"p_value": 1.0, "ci_low": 0.0, "ci_high": 1.0, "observed": 0.0}
    
    result = stats.binomtest(wins, total, p0, alternative='two-sided')
    ci = result.proportion_ci(confidence_level=0.95)
    
    return {
        "p_value": round(result.pvalue, 4),
        "ci_low": round(ci.low * 100, 1),
        "ci_high": round(ci.high * 100, 1),
        "observed": round(wins / total * 100, 2)
    }


def two_proportion_test(w1: int, n1: int, w2: int, n2: int) -> dict:
    """Two-proportion z-test (or Fisher's exact for small samples)."""
    if n1 == 0 or n2 == 0:
        return {"p_value": 1.0, "diff": 0.0}
    
    p1 = w1 / n1
    p2 = w2 / n2
    
    # Fisher's exact test (more appropriate for small samples)
    table = [[w1, n1 - w1], [w2, n2 - w2]]
    _, p_fisher = stats.fisher_exact(table, alternative='two-sided')
    
    return {
        "p_value": round(p_fisher, 4),
        "p1": round(p1 * 100, 2),
        "p2": round(p2 * 100, 2),
        "diff_pp": round((p1 - p2) * 100, 2),
        "n1": n1,
        "n2": n2
    }


def required_n_for_significance(observed_wr: float, p0: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """Estimate sample size needed to detect the observed effect with given power."""
    if observed_wr <= p0:
        return float('inf')
    
    from scipy.stats import norm
    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta = norm.ppf(power)
    
    p1 = observed_wr
    p_bar = (p0 + p1) / 2
    
    n = ((z_alpha * np.sqrt(2 * p_bar * (1 - p_bar)) + 
          z_beta * np.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) / (p1 - p0)) ** 2
    
    return int(np.ceil(n))


def main():
    db = SessionLocal()
    
    # ================================================================
    # Load all settled bets
    # ================================================================
    safe_bets = db.query(Bet).filter(
        Bet.portfolio_type == 'safe',
        Bet.result.in_(['won', 'lost'])
    ).all()
    
    all_bets = db.query(Bet).filter(
        Bet.portfolio_type == 'all_props',
        Bet.result.in_(['won', 'lost'])
    ).all()
    
    safe_keys = set((b.player_name, b.market, b.game_id) for b in safe_bets)
    non_rec = [b for b in all_bets if (b.player_name, b.market, b.game_id) not in safe_keys]
    
    s_won = len([b for b in safe_bets if b.result == 'won'])
    s_total = len(safe_bets)
    
    nr_won = len([b for b in non_rec if b.result == 'won'])
    nr_total = len(non_rec)
    
    a_won = len([b for b in all_bets if b.result == 'won'])
    a_total = len(all_bets)
    
    avg_odds = sum(b.odds for b in safe_bets) / len(safe_bets) if safe_bets else 1.82
    breakeven = 1.0 / avg_odds
    
    weeks_data = set()
    for b in safe_bets:
        weeks_data.add(b.week)
    
    print("=" * 70)
    print(f"📊 STATISTICAL SIGNIFICANCE TRACKER")
    print(f"   Weeks covered: {sorted(weeks_data)}")
    print(f"   Total settled (Safe): {s_total} | Avg Odds: {avg_odds:.3f} | Breakeven: {breakeven*100:.2f}%")
    print("=" * 70)
    
    # ================================================================
    # TEST 1: Safe WR vs Breakeven
    # ================================================================
    print("\n" + "─" * 70)
    print("TEST 1: Safe Win Rate vs Breakeven")
    print("─" * 70)
    
    t1 = binomial_test(s_won, s_total, breakeven)
    sig = "✅ SIGNIFICANT" if t1['p_value'] < 0.05 else "⏳ Not yet significant"
    n_needed = required_n_for_significance(s_won / s_total if s_total > 0 else 0.5, breakeven)
    
    print(f"  H₀: WR = {breakeven*100:.2f}% (breakeven)")
    print(f"  Observed: {t1['observed']}% ({s_won}W/{s_total - s_won}L)")
    print(f"  95% CI: [{t1['ci_low']}%, {t1['ci_high']}%]")
    print(f"  p-value: {t1['p_value']}")
    print(f"  Verdict: {sig}")
    if t1['p_value'] >= 0.05:
        print(f"  Est. sample needed for significance (80% power): ~{n_needed} bets")
        weeks_est = max(1, n_needed // 60)
        print(f"  At ~60 bets/week: ~{weeks_est} more weeks needed")
    
    # ================================================================
    # TEST 2: AI Recommended vs Not Recommended
    # ================================================================
    print("\n" + "─" * 70)
    print("TEST 2: AI Recommended vs Not Recommended")
    print("─" * 70)
    
    t2 = two_proportion_test(s_won, s_total, nr_won, nr_total)
    sig = "✅ SIGNIFICANT" if t2['p_value'] < 0.05 else "⏳ Not yet significant"
    
    print(f"  Recommended: {t2['p1']}% ({s_won}/{s_total})")
    print(f"  Not Recommended: {t2['p2']}% ({nr_won}/{nr_total})")
    print(f"  Difference: +{t2['diff_pp']}pp")
    print(f"  p-value (Fisher's exact): {t2['p_value']}")
    print(f"  Verdict: {sig}")
    
    # ================================================================
    # TEST 3: EV Brackets
    # ================================================================
    print("\n" + "─" * 70)
    print("TEST 3: EV Brackets (Low-Med vs High)")
    print("─" * 70)
    
    ev_low = [b for b in safe_bets if b.ev_percent and b.ev_percent < 8.0]
    ev_high = [b for b in safe_bets if b.ev_percent and b.ev_percent >= 8.0]
    
    elw = len([b for b in ev_low if b.result == 'won'])
    eln = len(ev_low)
    ehw = len([b for b in ev_high if b.result == 'won'])
    ehn = len(ev_high)
    
    t3 = two_proportion_test(elw, eln, ehw, ehn)
    sig = "✅ SIGNIFICANT" if t3['p_value'] < 0.05 else "⏳ Not yet significant"
    
    print(f"  EV <8%: {t3['p1']}% ({elw}/{eln})")
    print(f"  EV ≥8%: {t3['p2']}% ({ehw}/{ehn})")
    print(f"  Difference: +{t3['diff_pp']}pp")
    print(f"  p-value (Fisher's exact): {t3['p_value']}")
    print(f"  Verdict: {sig}")
    
    # ================================================================
    # TEST 4: Under vs Over
    # ================================================================
    print("\n" + "─" * 70)
    print("TEST 4: Under vs Over")
    print("─" * 70)
    
    unders = [b for b in safe_bets if b.side and 'under' in b.side.lower()]
    overs = [b for b in safe_bets if b.side and 'over' in b.side.lower()]
    
    uw = len([b for b in unders if b.result == 'won'])
    un = len(unders)
    ow = len([b for b in overs if b.result == 'won'])
    on = len(overs)
    
    t4 = two_proportion_test(uw, un, ow, on)
    sig = "✅ SIGNIFICANT" if t4['p_value'] < 0.05 else "⏳ Not yet significant"
    
    print(f"  Under: {t4['p1']}% ({uw}/{un})")
    print(f"  Over:  {t4['p2']}% ({ow}/{on})")
    print(f"  Difference: +{t4['diff_pp']}pp")
    print(f"  p-value (Fisher's exact): {t4['p_value']}")
    print(f"  Verdict: {sig}")
    
    # ================================================================
    # TEST 5: Market breakdown
    # ================================================================
    print("\n" + "─" * 70)
    print("TEST 5: Market Win Rates vs Breakeven")
    print("─" * 70)
    
    for market in ['passing_yards', 'rushing_yards', 'receiving_yards']:
        mb = [b for b in safe_bets if b.market == market]
        mw = len([b for b in mb if b.result == 'won'])
        mn = len(mb)
        if mn > 0:
            t = binomial_test(mw, mn, breakeven)
            sig_icon = "✅" if t['p_value'] < 0.05 else "⏳"
            print(f"  {market:20s}: {t['observed']}% ({mw}/{mn})  CI=[{t['ci_low']}%,{t['ci_high']}%]  p={t['p_value']}  {sig_icon}")
    
    # ================================================================
    # TEST 6: Brier Score (Calibration)
    # ================================================================
    print("\n" + "─" * 70)
    print("TEST 6: Model Calibration (Brier Score)")
    print("─" * 70)
    
    brier_scores = []
    for b in safe_bets:
        if b.model_probability and 0 < b.model_probability < 1:
            actual = 1.0 if b.result == 'won' else 0.0
            # model_probability is already P(win for the bet side) in bets table
            p_win = b.model_probability
            brier_scores.append((p_win - actual) ** 2)
    
    if brier_scores:
        brier = np.mean(brier_scores)
        # Reference: always predicting breakeven probability
        brier_ref = np.mean([(breakeven - (1.0 if b.result == 'won' else 0.0)) ** 2 for b in safe_bets])
        brier_skill = 1.0 - brier / brier_ref if brier_ref > 0 else 0.0
        
        print(f"  Brier Score: {brier:.4f} (lower is better)")
        print(f"  Reference (naive): {brier_ref:.4f}")
        print(f"  Brier Skill Score: {brier_skill:.4f} ({'positive = better than naive' if brier_skill > 0 else 'negative = worse than naive'})")
        print(f"  Calibrated bets: {len(brier_scores)}/{s_total}")
    else:
        print("  No model probabilities available for Brier score calculation")
    
    # ================================================================
    # SUMMARY TABLE
    # ================================================================
    print("\n" + "=" * 70)
    print("📋 SIGNIFICANCE SUMMARY")
    print("=" * 70)
    print(f"{'Test':<40} {'p-value':>8} {'Status':>20}")
    print("-" * 70)
    
    tests = [
        ("Safe WR vs Breakeven", t1['p_value']),
        ("AI Rec vs Not-Rec", t2['p_value']),
        ("EV <8% vs ≥8%", t3['p_value']),
        ("Under vs Over", t4['p_value']),
    ]
    
    for name, p in tests:
        status = "✅ Confirmed" if p < 0.05 else ("🔶 Suggestive" if p < 0.20 else "⏳ No signal")
        print(f"  {name:<38} {p:>8.4f} {status:>20}")
    
    print("\n" + "─" * 70)
    print("Legend: ✅ p<0.05 (act on it)  🔶 p<0.20 (monitor)  ⏳ p≥0.20 (noise)")
    print("─" * 70)
    
    db.close()


if __name__ == "__main__":
    main()
