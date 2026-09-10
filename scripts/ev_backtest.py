from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

# ---------------------------------------------------------------------------
# 1. CONFIGURAÇÃO
# ---------------------------------------------------------------------------

# Caminhos
PREDICTIONS_PATH = "data/model_predictions.parquet"
ODDS_PATH = "data/betclic_parsed_odds.parquet"
OUTPUT_REPORT_PATH = "reports/ev_backtest_report.txt"
OUTPUT_DETAIL_CSV = "reports/ev_backtest_detail.csv"

EV_THRESHOLD = 0.02
EV_BINS = [-np.inf, 0.00, 0.02, 0.05, 0.10, np.inf]
EV_BIN_LABELS = ["EV<0", "0-2%", "2-5%", "5-10%", ">10%"]
Z_BINS = [0, 0.25, 0.5, 1.0, 1.5, np.inf]
Z_BIN_LABELS = ["0-0.25σ", "0.25-0.5σ", "0.5-1.0σ", "1.0-1.5σ", ">1.5σ"]

# ---------------------------------------------------------------------------
# 2. CARREGAMENTO DE DADOS
# ---------------------------------------------------------------------------

def load_predictions() -> pd.DataFrame:
    df = pd.read_parquet(PREDICTIONS_PATH)
    return df

def load_odds() -> pd.DataFrame:
    df = pd.read_parquet(ODDS_PATH)
    return df

# ---------------------------------------------------------------------------
# 3. CÁLCULO DE PROBABILIDADE E EV
# ---------------------------------------------------------------------------

def prob_over(line: float, quantiles: list[float], alpha_levels: list[float]) -> float:
    """
    Usa os quantis previstos pelo modelo XGBoost Quantile Regressor para interpolar
    a probabilidade empírica de P(Y > line), sem assumir distribuição normal.
    """
    from scipy import interpolate
    import numpy as np
    
    if not quantiles or len(quantiles) != len(alpha_levels):
        return 0.5
        
    q = np.sort(quantiles)
    # Pad com 0 no começo e um valor alto no final para fechar a CDF
    x = np.concatenate(([0], q, [q[-1] * 1.5 + 10]))
    y = np.concatenate(([0.0], alpha_levels, [1.0]))
    
    # Garantir que x seja estritamente crescente
    dx = np.diff(x)
    if np.any(dx <= 0):
        x = x + np.linspace(0, 1e-4, len(x))
        
    interp_cdf = interpolate.interp1d(x, y, kind='linear', bounds_error=False, fill_value=(0.0, 1.0))
    prob_under = interp_cdf(line)
    return 1.0 - prob_under

def calculate_ev(prob_win: float, decimal_odds: float, stake: float = 1.0) -> float:
    return prob_win * (decimal_odds - 1) * stake - (1 - prob_win) * stake

def z_distance(line: float, pred_mean: float, pred_std: float) -> float:
    if pred_std <= 0:
        return np.nan
    return abs(line - pred_mean) / pred_std

# ---------------------------------------------------------------------------
# 4. MONTAGEM DO DATASET
# ---------------------------------------------------------------------------

def build_bet_dataset(preds: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    df = preds.merge(odds, on=["player_id", "season", "week", "market"], how="inner")
    df["p_over"] = df.apply(lambda r: prob_over(r["line"], r["pred_mean"], r["pred_std"]), axis=1)
    df["p_under"] = 1.0 - df["p_over"]
    df["ev_over"] = df.apply(lambda r: calculate_ev(r["p_over"], r["odds_over"]), axis=1)
    df["ev_under"] = df.apply(lambda r: calculate_ev(r["p_under"], r["odds_under"]), axis=1)

    df["suggested_side"] = np.where(df["ev_over"] >= df["ev_under"], "over", "under")
    df["suggested_ev"] = np.where(df["ev_over"] >= df["ev_under"], df["ev_over"], df["ev_under"])
    df["suggested_prob"] = np.where(df["ev_over"] >= df["ev_under"], df["p_over"], df["p_under"])
    df["suggested_odds"] = np.where(df["ev_over"] >= df["ev_under"], df["odds_over"], df["odds_under"])

    df["actual_over"] = (df["actual_value"] > df["line"]).astype(int)
    df["bet_won"] = np.where(df["suggested_side"] == "over", df["actual_over"], 1 - df["actual_over"])

    df["pnl"] = np.where(df["bet_won"] == 1, df["suggested_odds"] - 1, -1)
    df["z_distance"] = df.apply(lambda r: z_distance(r["line"], r["pred_mean"], r["pred_std"]), axis=1)

    return df

# ---------------------------------------------------------------------------
# 5. ANÁLISE DE CALIBRAÇÃO
# ---------------------------------------------------------------------------

def calibration_by_ev_bin(df: pd.DataFrame) -> pd.DataFrame:
    bets = df[df["suggested_ev"] >= EV_THRESHOLD].copy()
    bets["ev_bin"] = pd.cut(bets["suggested_ev"], bins=EV_BINS, labels=EV_BIN_LABELS)
    summary = bets.groupby("ev_bin", observed=True).agg(
        n_bets=("bet_won", "size"),
        win_rate=("bet_won", "mean"),
        avg_predicted_prob=("suggested_prob", "mean"),
        avg_pnl=("pnl", "mean"),
        total_pnl=("pnl", "sum"),
    ).reset_index()
    summary["roi_pct"] = (summary["total_pnl"] / summary["n_bets"]) * 100
    return summary

def calibration_by_tail_bin(df: pd.DataFrame) -> pd.DataFrame:
    bets = df[df["suggested_ev"] >= EV_THRESHOLD].copy()
    bets["z_bin"] = pd.cut(bets["z_distance"], bins=Z_BINS, labels=Z_BIN_LABELS)
    summary = bets.groupby("z_bin", observed=True).agg(
        n_bets=("bet_won", "size"),
        win_rate=("bet_won", "mean"),
        avg_predicted_prob=("suggested_prob", "mean"),
        avg_pnl=("pnl", "mean"),
        total_pnl=("pnl", "sum"),
    ).reset_index()
    summary["roi_pct"] = (summary["total_pnl"] / summary["n_bets"]) * 100
    summary["calibration_gap"] = summary["win_rate"] - summary["avg_predicted_prob"]
    return summary

def calibration_by_market(df: pd.DataFrame) -> pd.DataFrame:
    bets = df[df["suggested_ev"] >= EV_THRESHOLD].copy()
    summary = bets.groupby("market").agg(
        n_bets=("bet_won", "size"),
        win_rate=("bet_won", "mean"),
        avg_predicted_prob=("suggested_prob", "mean"),
        total_pnl=("pnl", "sum"),
    ).reset_index()
    summary["roi_pct"] = (summary["total_pnl"] / summary["n_bets"]) * 100
    summary["calibration_gap"] = summary["win_rate"] - summary["avg_predicted_prob"]
    return summary

# ---------------------------------------------------------------------------
# 6. RELATÓRIO
# ---------------------------------------------------------------------------

def build_report(df: pd.DataFrame, ev_summary: pd.DataFrame,
                  tail_summary: pd.DataFrame, market_summary: pd.DataFrame) -> str:
    n_total_bets = len(df[df["suggested_ev"] >= EV_THRESHOLD])
    total_pnl = df.loc[df["suggested_ev"] >= EV_THRESHOLD, "pnl"].sum()
    overall_roi = (total_pnl / n_total_bets * 100) if n_total_bets else float("nan")

    lines = []
    lines.append("=" * 70)
    lines.append("EV BACKTEST REPORT")
    lines.append("=" * 70)
    lines.append(f"Total de apostas simuladas (EV >= {EV_THRESHOLD:.0%}): {n_total_bets}")
    lines.append(f"ROI geral simulado: {overall_roi:.2f}%")
    lines.append("")
    lines.append("-" * 70)
    lines.append("Calibração por bin de EV previsto")
    lines.append("-" * 70)
    lines.append(ev_summary.to_string(index=False))
    lines.append("")
    lines.append("-" * 70)
    lines.append("Calibração por distância da linha (proxy de cauda, em desvios-padrão)")
    lines.append("-" * 70)
    lines.append(tail_summary.to_string(index=False))
    lines.append("")
    lines.append("-" * 70)
    lines.append("Calibração por mercado (passing / rushing / receiving)")
    lines.append("-" * 70)
    lines.append(market_summary.to_string(index=False))
    lines.append("=" * 70)
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 7. MAIN
# ---------------------------------------------------------------------------

def main():
    try:
        preds = load_predictions()
        odds = load_odds()
        bets_df = build_bet_dataset(preds, odds)

        ev_summary = calibration_by_ev_bin(bets_df)
        tail_summary = calibration_by_tail_bin(bets_df)
        market_summary = calibration_by_market(bets_df)

        report = build_report(bets_df, ev_summary, tail_summary, market_summary)
        print(report)

        import os
        os.makedirs("reports", exist_ok=True)
        with open(OUTPUT_REPORT_PATH, "w") as f:
            f.write(report)

        bets_df.to_csv(OUTPUT_DETAIL_CSV, index=False)
        print(f"\nRelatório salvo em: {OUTPUT_REPORT_PATH}")
    except Exception as e:
        print(f"EV Backtest pendente ou sem dados de entrada: {e}")

if __name__ == "__main__":
    main()
