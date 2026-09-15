"""Unit tests and empirical validation benchmark for probability calibration layer."""

import os
from pathlib import Path
import numpy as np
import polars as pl
import pytest

from nfl_odds.betting.ev_calc import analyze_opportunities
from nfl_odds.models.calibration import ProbabilityCalibrator
from nfl_odds.models.train import PlayerPropModel


class TestProbabilityCalibratorUnit:
    """Unit tests verifying invariants of ProbabilityCalibrator."""

    def test_bounds_and_input_sanitization(self):
        cal = ProbabilityCalibrator(method="platt")
        # Train on simple monotonic data
        p_tr = np.array([0.2, 0.4, 0.6, 0.8])
        y_tr = np.array([0.0, 0.0, 1.0, 1.0])
        cal.fit(p_tr, y_tr)

        # Test corrupt / edge-case inputs
        corrupt_inputs = np.array([np.nan, np.inf, -np.inf, -10.0, 0.0, 1.0, 5.0])
        res = cal.calibrate(corrupt_inputs)

        assert not np.any(np.isnan(res)), "Output contains NaNs"
        assert not np.any(np.isinf(res)), "Output contains Infs"
        assert np.all(res >= 0.0001), f"Output violates lower bound: {res.min()}"
        assert np.all(res <= 0.9999), f"Output violates upper bound: {res.max()}"

    def test_monotonicity_and_positive_slope_guard(self):
        cal = ProbabilityCalibrator(method="platt")
        # Inverted data where raw probabilities are negatively correlated with outcomes
        p_tr = np.array([0.9, 0.8, 0.2, 0.1])
        y_tr = np.array([0.0, 0.0, 1.0, 1.0])
        cal.fit(p_tr, y_tr)

        # Positive slope guard must enforce slope >= 0.01
        assert cal.slope_ >= 0.01, f"Slope guard failed, got slope: {cal.slope_}"

        # Monotonicity test across spectrum
        test_probs = np.linspace(0.001, 0.999, 500)
        cal_probs = cal.calibrate(test_probs)
        assert np.all(np.diff(cal_probs) > 0), "Calibrated probabilities must be strictly monotonic"

    def test_binary_point_symmetry(self):
        cal = ProbabilityCalibrator(method="platt")
        p_tr = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        y_tr = np.array([0.0, 0.0, 1.0, 1.0, 1.0])
        cal.fit(p_tr, y_tr)

        # Intercept must be identically zero
        assert cal.intercept_ == 0.0, f"Intercept must be 0.0, got: {cal.intercept_}"

        test_probs = np.linspace(0.001, 0.999, 100)
        cal_p = cal.calibrate(test_probs)
        cal_comp = cal.calibrate(1.0 - test_probs)

        # P(Under) = 1.0 - P(Over)
        assert np.allclose(cal_p + cal_comp, 1.0, atol=1e-7), (
            f"Point-symmetry failed: max dev = {np.max(np.abs(cal_p + cal_comp - 1.0))}"
        )
        # At 0.5, output must be exactly 0.5
        assert np.isclose(cal.calibrate(np.array([0.5]))[0], 0.5, atol=1e-6)

    def test_isotonic_method(self):
        cal = ProbabilityCalibrator(method="isotonic")
        p_tr = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        y_tr = np.array([0.0, 0.0, 1.0, 1.0, 1.0])
        cal.fit(p_tr, y_tr)

        test_probs = np.array([0.2, 0.5, 0.8])
        cal_probs = cal.calibrate(test_probs)
        assert np.all(cal_probs >= 0.0001) and np.all(cal_probs <= 0.9999)
        assert cal_probs[0] <= cal_probs[1] <= cal_probs[2]

    def test_persistence_dict_and_joblib(self, tmp_path):
        cal = ProbabilityCalibrator(method="platt", C=0.75)
        p_tr = np.array([0.2, 0.4, 0.6, 0.8])
        y_tr = np.array([0.0, 1.0, 0.0, 1.0])
        cal.fit(p_tr, y_tr)

        test_p = np.array([0.25, 0.5, 0.75])
        expected = cal.calibrate(test_p)

        # 1. to_dict / from_dict
        state = cal.to_dict()
        cal_dict = ProbabilityCalibrator.from_dict(state)
        assert np.allclose(cal_dict.calibrate(test_p), expected)

        # 2. save / load
        save_path = tmp_path / "test_cal.joblib"
        cal.save(save_path)
        cal_loaded = ProbabilityCalibrator.load(save_path)
        assert np.allclose(cal_loaded.calibrate(test_p), expected)

    def test_invalid_method_raises(self):
        with pytest.raises(ValueError, match="Unknown calibration method"):
            ProbabilityCalibrator(method="non_existent")

    def test_fit_length_mismatch_raises(self):
        cal = ProbabilityCalibrator(method="platt")
        with pytest.raises(ValueError, match="Length mismatch"):
            cal.fit([0.2, 0.4], [1.0])

    def test_unfitted_calibrator_clamps(self):
        cal = ProbabilityCalibrator()
        assert not cal.is_fitted
        res = cal.calibrate(np.array([-1.0, 0.5, 2.0]))
        assert np.isclose(res[0], 0.0001)
        assert np.isclose(res[1], 0.5)
        assert np.isclose(res[2], 0.9999)


class TestPlayerPropModelIntegration:
    """Tests verifying PlayerPropModel dual serialization and calibration execution."""

    def test_dual_serialization_fallback(self, tmp_path):
        model = PlayerPropModel(target="passing_yards")
        model.features = ["pass_attempts_avg_5"]
        
        # Save without calibrator
        model_path = tmp_path / "passing_yards_model.joblib"
        model.save(str(model_path))

        # Separate calibrator file
        cal = ProbabilityCalibrator(method="platt")
        cal.slope_ = 0.85
        cal.intercept_ = 0.0
        cal.is_fitted = True
        cal_path = tmp_path / "passing_yards_calibrator.joblib"
        cal.save(cal_path)

        # Loading model should automatically detect and load adjacent calibrator
        loaded_model = PlayerPropModel.load(str(model_path))
        assert loaded_model.calibrator is not None
        assert np.isclose(loaded_model.calibrator.slope_, 0.85)

    def test_bundled_serialization(self, tmp_path):
        model = PlayerPropModel(target="rushing_yards")
        model.features = ["rush_attempts_avg_5"]
        cal = ProbabilityCalibrator(method="platt")
        cal.slope_ = 0.52
        cal.intercept_ = 0.0
        cal.is_fitted = True
        model.calibrator = cal

        bundle_path = tmp_path / "rushing_yards_model.joblib"
        model.save(str(bundle_path))

        loaded = PlayerPropModel.load(str(bundle_path))
        assert loaded.calibrator is not None
        assert np.isclose(loaded.calibrator.slope_, 0.52)

    def test_model_probability_over_line_monotonicity_across_lines(self):
        model = PlayerPropModel.load("data/passing_yards_model.joblib")
        df = pl.read_parquet("data/live_features.parquet").filter(pl.col("position") == "QB").head(1)
        lines = np.array([150.5, 200.5, 250.5, 300.5])
        df_multi = pl.concat([df] * len(lines))
        probs_cal = model.probability_over_line(df_multi, lines, calibrate=True)
        probs_raw = model.probability_over_line(df_multi, lines, calibrate=False)

        assert np.all(np.diff(probs_cal) <= 0), "Calibrated P(Over) must be non-increasing with line"
        assert np.all(np.diff(probs_raw) <= 0), "Raw P(Over) must be non-increasing with line"
        assert np.all((probs_cal >= 0.0001) & (probs_cal <= 0.9999))

    def test_probability_over_line_uncalibrated_mode(self):
        model = PlayerPropModel.load("data/passing_yards_model.joblib")
        df = pl.read_parquet("data/live_features.parquet").filter(pl.col("position") == "QB").head(2)
        lines = np.array([200.5, 250.5])
        probs = model.probability_over_line(df, lines, calibrate=False)
        assert len(probs) == 2
        assert np.all((probs >= 0.0001) & (probs <= 0.9999))


class TestEvCalcDefensiveClamping:
    """Tests verifying ev_calc prevents division by zero with extreme probabilities."""

    def test_analyze_opportunities_bounds(self):
        df_odds = pl.DataFrame({
            "odds": [2.0, 1.9, 2.5],
            "side": ["over", "under", "over"],
            "line": [250.5, 45.5, 60.5],
        })
        extreme_probs = np.array([0.0, 1.0, 0.5])
        df_res = analyze_opportunities(df_odds, extreme_probs)

        fair_odds = df_res["fair_odds"].to_numpy()
        assert not np.any(np.isnan(fair_odds)), "Fair odds contain NaNs"
        assert not np.any(np.isinf(fair_odds)), "Fair odds contain Infs"
        assert np.all(fair_odds > 1.0) and np.all(fair_odds <= 10000.0)


class TestMultiMarketHoldoutBenchmark:
    """Empirical benchmark verifying calibration achieves BSS > 0 on temporal holdout data."""

    @pytest.mark.parametrize(
        "market,positions,min_line",
        [
            ("passing_yards", ["QB"], 20.0),
            ("rushing_yards", ["RB", "WR", "QB"], 5.0),
            ("receiving_yards", ["WR", "TE", "RB"], 5.0),
        ],
    )
    def test_market_holdout_bss_positive(self, market: str, positions: list, min_line: float):
        features_path = Path("data/live_features.parquet")
        model_path = Path(f"data/{market}_model.joblib")

        if not features_path.exists() or not model_path.exists():
            pytest.skip(f"Prerequisite files for {market} not found.")

        df = pl.read_parquet(str(features_path))
        model = PlayerPropModel.load(str(model_path))

        sub = df.filter(pl.col("position").is_in(positions)).drop_nulls(
            subset=model.features + [market]
        )
        line_col = f"{market}_avg_5"
        sub = sub.filter(pl.col(line_col) > min_line)

        # Temporal split: weeks 1-14 train, weeks 15-22 holdout
        train = sub.filter(pl.col("week") <= 14)
        val = sub.filter(pl.col("week") > 14)

        assert len(train) > 0, f"No train rows for {market}"
        assert len(val) > 0, f"No validation rows for {market}"

        # Train calibrator across line variants on train split
        base_lines_tr = train[line_col].to_numpy()
        p_tr_all: list = []
        y_tr_all: list = []

        for mult in [0.85, 1.0, 1.15]:
            lines = np.round(base_lines_tr * mult * 2) / 2.0
            p_tr_all.extend(model.probability_over_line(train, lines, calibrate=False))
            y_tr_all.extend((train[market].to_numpy() > lines).astype(float))

        calibrator = ProbabilityCalibrator(method="platt", C=0.5)
        calibrator.fit(p_tr_all, y_tr_all)

        # Evaluate on validation holdout
        val_lines = val[line_col].to_numpy()
        val_y = (val[market].to_numpy() > val_lines).astype(float)

        raw_p = model.probability_over_line(val, val_lines, calibrate=False)
        cal_p = calibrator.calibrate(raw_p)

        # Baseline: naive 0.5 predictor
        ref_brier = float(np.mean((0.5 - val_y) ** 2))
        raw_brier = float(np.mean((raw_p - val_y) ** 2))
        cal_brier = float(np.mean((cal_p - val_y) ** 2))

        raw_bss = 1.0 - raw_brier / ref_brier
        cal_bss = 1.0 - cal_brier / ref_brier

        print(
            f"\nBenchmark [{market}] N_val={len(val_y)}: "
            f"Raw Brier={raw_brier:.4f} (BSS={raw_bss:+.4f}) -> "
            f"Cal Brier={cal_brier:.4f} (BSS={cal_bss:+.4f}) | "
            f"Fitted slope w={calibrator.slope_:.4f}"
        )

        # Invariant 1: Calibrated Brier Skill Score must be strictly positive
        assert cal_bss > 0, f"Calibrated BSS must be > 0 on holdout for {market}, got: {cal_bss:.4f}"
        # Invariant 2: Calibrated Brier must be lower than or equal to raw Brier
        assert cal_brier <= raw_brier, (
            f"Calibration must improve or maintain Brier score on {market}: "
            f"cal={cal_brier:.4f} vs raw={raw_brier:.4f}"
        )


class TestApiIntegrationZeroRegression:
    """Zero-regression test suite for dashboard API /api/predict integration."""

    def test_api_predict_manual_override_preserves_schema(self):
        from fastapi.testclient import TestClient
        from nfl_odds.dashboard.api import app

        client = TestClient(app)
        res = client.post(
            "/api/predict",
            json={
                "manual_prob_over": 60.0,
                "odds_over": 2.0,
                "odds_under": 1.8,
                "stake": 100.0,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["over"]["model_prob"] == 0.6
        assert data["over"]["fair_odds"] == 1.67
        assert data["over"]["ev"] == 20.0
        assert "half_kelly_percent" in data["over"]
        assert "recommended_stake" in data["over"]
        assert data["under"]["model_prob"] == 0.4

    def test_api_predict_model_calibration_and_schema(self):
        from fastapi.testclient import TestClient
        from nfl_odds.dashboard.api import app

        client = TestClient(app)
        res = client.post(
            "/api/predict",
            json={
                "player_name": "Patrick Mahomes",
                "market": "passing_yards",
                "line": 260.5,
                "odds_over": 1.91,
                "odds_under": 1.91,
                "stake": 100.0,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert 0.0001 <= data["over"]["model_prob"] <= 0.9999
        assert 0.0001 <= data["under"]["model_prob"] <= 0.9999
        assert round(data["over"]["model_prob"] + data["under"]["model_prob"], 4) == 1.0

        for side in ("over", "under"):
            assert "model_prob" in data[side]
            assert "implied_prob" in data[side]
            assert "fair_odds" in data[side]
            assert "edge" in data[side]
            assert "ev" in data[side]
            assert "profit" in data[side]
            assert "kelly_percent" in data[side]
            assert "half_kelly_percent" in data[side]
            assert "recommended_stake" in data[side]

