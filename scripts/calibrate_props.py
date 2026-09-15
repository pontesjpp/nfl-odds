#!/usr/bin/env python
"""Train and persist probability calibrators for all active prop markets."""

import os
from pathlib import Path
import numpy as np
import polars as pl
from nfl_odds.models.calibration import ProbabilityCalibrator
from nfl_odds.models.train import PlayerPropModel

MARKETS_CONFIG = {
    "passing_yards": {
        "positions": ["QB"],
        "line_col": "passing_yards_avg_5",
        "min_line": 20.0,
    },
    "rushing_yards": {
        "positions": ["RB", "WR", "QB"],
        "line_col": "rushing_yards_avg_5",
        "min_line": 5.0,
    },
    "receiving_yards": {
        "positions": ["WR", "TE", "RB"],
        "line_col": "receiving_yards_avg_5",
        "min_line": 5.0,
    },
}


def train_market_calibrator(
    market: str,
    config: dict,
    df_features: pl.DataFrame,
    method: str = "platt",
    data_dir: Path = Path("data"),
) -> ProbabilityCalibrator:
    """Train ProbabilityCalibrator for a specific market using 2025 player features."""
    model_path = data_dir / f"{market}_model.joblib"
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    model = PlayerPropModel.load(str(model_path))

    pos = config["positions"]
    sub = df_features.filter(pl.col("position").is_in(pos)).drop_nulls(
        subset=model.features + [market]
    )

    line_col = config["line_col"]
    if line_col in sub.columns:
        sub = sub.filter(pl.col(line_col) > config["min_line"])
        base_lines = sub[line_col].to_numpy()
    else:
        # Fallback to model median prediction
        preds = model.predict_distribution(sub)
        base_lines = preds[:, len(model.quantiles) // 2]

    # Generate training instances across line variants (spread across the market line spectrum)
    p_tr_all: list = []
    y_tr_all: list = []

    for mult in [0.85, 0.95, 1.0, 1.05, 1.15]:
        lines = np.round(base_lines * mult * 2) / 2.0
        # Calculate raw uncalibrated probabilities
        raw_p = model.probability_over_line(sub, lines, calibrate=False)
        actual_y = (sub[market].to_numpy() > lines).astype(float)
        p_tr_all.extend(raw_p)
        y_tr_all.extend(actual_y)

    p_arr = np.array(p_tr_all)
    y_arr = np.array(y_tr_all)

    calibrator = ProbabilityCalibrator(method=method, C=0.5)
    calibrator.fit(p_arr, y_arr)

    print(
        f"[{market}] Fitted {method} calibrator on {len(p_arr)} samples | "
        f"Slope w={calibrator.slope_:.4f}, Intercept b={calibrator.intercept_:.4f}"
    )

    # Persist as standalone calibrator joblib
    cal_path = data_dir / f"{market}_calibrator.joblib"
    calibrator.save(str(cal_path))
    print(f"[{market}] Saved standalone calibrator to: {cal_path}")

    # Attach to model and update model bundle for dual serialization
    model.calibrator = calibrator
    model.save(str(model_path))
    print(f"[{market}] Updated model bundle at: {model_path}")

    return calibrator


def main():
    data_dir = Path("data")
    features_path = data_dir / "live_features.parquet"
    if not features_path.exists():
        raise FileNotFoundError(f"Feature data not found: {features_path}")

    print(f"Loading features from {features_path}...")
    df_features = pl.read_parquet(str(features_path))

    for market, config in MARKETS_CONFIG.items():
        print(f"\n--- Calibrating market: {market} ---")
        train_market_calibrator(market, config, df_features, method="platt", data_dir=data_dir)

    print("\nCalibration completed for all markets.")


if __name__ == "__main__":
    main()
