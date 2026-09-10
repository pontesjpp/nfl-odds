"""
AUDITORIA E REPRODUCIBILIDADE TÉCNICA - MODELO NFL PLAYER PROPS
Temporada de Teste: 2025 (Fora da Amostra)
Semente Fixada: seed = 42

Instruções de execução:
    python3 scripts/reproduce_audit.py
"""

from __future__ import annotations

import numpy as np
import polars as pl
from scipy.stats import norm

from nfl_odds.models.train import PlayerPropModel
from nfl_odds.data.collect_nfl import load_player_stats


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Calcula intervalo de confiança de Wilson Score para proporções binomiais."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + (z**2) / n
    center = (p + (z**2) / (2 * n)) / denom
    spread = z * np.sqrt(p * (1 - p) / n + (z**2) / (4 * n**2)) / denom
    return max(0.0, center - spread), min(1.0, center + spread)


def run_full_audit():
    print("=" * 70)
    print("RELATÓRIO DE AUDITORIA ESTATÍSTICA REPRODUZÍVEL")
    print("=" * 70)

    # 1. Carregamento de dados
    df_stats = load_player_stats([2024, 2025])
    df_features = pl.read_parquet("data/live_features.parquet")

    actuals = df_stats.filter(pl.col("season") == 2025).select([
        "player_id", "season", "week", "passing_yards", "rushing_yards", "receiving_yards"
    ])

    markets = [
        ("rushing_yards", ["RB", "WR", "QB"]),
        ("receiving_yards", ["WR", "TE", "RB"]),
        ("passing_yards", ["QB"]),
    ]

    thresholds_grid = [0.0, 5.0, 10.0, 12.0, 15.0, 18.0, 20.0, 25.0, 30.0, 35.0, 40.0]

    for market, positions in markets:
        print(f"\n>>> MERCADO: {market.upper()} <<<")
        model = PlayerPropModel.load(f"data/{market}_model.joblib")

        eval_df = df_features.filter(pl.col("season") == 2025).filter(pl.col("position").is_in(positions))
        eval_df = eval_df.drop_nulls(subset=model.features)

        eval_joined = eval_df.join(
            actuals.select(["player_id", "season", "week", market]),
            on=["player_id", "season", "week"],
            how="inner"
        ).drop_nulls(subset=[market])

        preds = model.predict_distribution(eval_joined)
        y_true = eval_joined[market].to_numpy()
        p50 = preds[:, 3]  # Mediana
        baseline = eval_joined[f"{market}_avg_5"].to_numpy()
        weeks = eval_joined["week"].to_numpy()
        unique_weeks = np.unique(weeks)

        n_total = len(y_true)
        print(f"Volume Amostral Total: N = {n_total} atuações | Semanas: {len(unique_weeks)}")

        # ---------------------------------------------------------------------
        # Curva de Sensibilidade de Threshold (Post-Hoc Sensitivity Curve)
        # ---------------------------------------------------------------------
        print("\n[1] Curva de Sensibilidade de Limiar (Threshold na Média Móvel de 5 Jogos)")
        print("Thresh | Retained N (%) | Accuracy | 95% Cluster CI (Week) | p-val vs 54.9%")
        print("-" * 72)

        for th in thresholds_grid:
            mask = baseline >= th
            n_sub = int(mask.sum())
            if n_sub < 50:
                continue

            pct_retained = (n_sub / n_total) * 100
            correct = ((p50[mask] > baseline[mask]) == (y_true[mask] > baseline[mask])).astype(float)
            acc = correct.mean() * 100

            sub_weeks = weeks[mask]
            u_w = np.unique(sub_weeks)
            week_data = [correct[sub_weeks == w] for w in u_w]
            n_w = len(u_w)

            np.random.seed(42)
            boot_means = []
            for _ in range(5000):
                idx = np.random.choice(n_w, size=n_w, replace=True)
                sampled = np.concatenate([week_data[i] for i in idx])
                boot_means.append(sampled.mean() * 100)

            ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
            p_val = float((np.array(boot_means) <= 54.9).mean())

            print(f"{th:6.1f} | {n_sub:5d} ({pct_retained:4.1f}%) | {acc:7.2f}% | [{ci_low:5.2f}%, {ci_high:5.2f}%] | {p_val:8.4f}")

        # ---------------------------------------------------------------------
        # Calibração Empírica de Todos os Quantis
        # ---------------------------------------------------------------------
        print(f"\n[2] Calibração Empírica dos Quantis (Amostra Integral N={n_total})")
        print("Quantil | Realizado | Desvio  | 95% IC (Wilson)   | Hits / Total")
        print("-" * 62)
        for i, q in enumerate(model.quantiles):
            hits = int((y_true <= preds[:, i]).sum())
            rate = hits / n_total
            ci_low, ci_high = wilson_ci(hits, n_total)
            gap = rate - q
            print(f"{q*100:6.1f}% | {rate*100:8.1f}% | {gap*100:+6.1f}% | [{ci_low*100:5.1f}%, {ci_high*100:5.1f}%] | {hits:5d} / {n_total:5d}")


if __name__ == "__main__":
    run_full_audit()
