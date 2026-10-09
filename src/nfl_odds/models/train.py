import xgboost as xgb
import polars as pl
import numpy as np
from typing import List, Tuple, Dict, Optional, Union
from scipy import interpolate, stats

class PlayerPropModel:
    def __init__(self, target: str, quantiles: List[float] = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]):
        self.target = target
        self.quantiles = quantiles
        self.model = xgb.XGBRegressor(
            objective='reg:quantileerror',
            quantile_alpha=self.quantiles,
            n_estimators=100,
            learning_rate=0.05,
            max_depth=4,
            random_state=42
        )
        self.features = []
        self.calibrator = None
        
    def fit(self, df: pl.DataFrame, features: List[str], sample_weight: np.ndarray = None):
        self.features = features
        
        # 4. Stub Stability Check: explicitly crash if a feature is completely null
        null_counts = df.select(features).null_count().row(0)
        for i, col in enumerate(features):
            if null_counts[i] == len(df):
                raise ValueError(f"CRITICAL: Feature '{col}' is 100% NULL (possível stub não resolvido ou falha de merge). Abortando treino.")
            elif null_counts[i] > len(df) * 0.5:
                print(f"WARNING: Feature '{col}' tem mais de 50% de valores nulos.")
                
        # Drop rows with nulls in target or features while preserving sample_weights alignment
        if sample_weight is not None and len(sample_weight) == len(df):
            df = df.with_columns(pl.Series("__sample_weight__", sample_weight))
            df_clean = df.drop_nulls(subset=features + [self.target])
            weights_clean = df_clean["__sample_weight__"].to_numpy()
        else:
            df_clean = df.drop_nulls(subset=features + [self.target])
            weights_clean = None

        if len(df_clean) == 0:
            raise ValueError("CRITICAL: Todos os dados foram descartados após remover nulos. Verifique os stubs e o join.")
        
        X = df_clean.select(features).to_numpy()
        y = df_clean.select(self.target).to_series().to_numpy()
        
        if weights_clean is not None:
            self.model.fit(X, y, sample_weight=weights_clean)
        else:
            self.model.fit(X, y)
        return self
        
    def save(self, path: str):
        import joblib
        bundle = {
            "model": self.model,
            "features": self.features,
            "quantiles": self.quantiles,
            "target": self.target,
            "calibrator": self.calibrator.to_dict() if self.calibrator is not None else None,
        }
        joblib.dump(bundle, path)
        
    @classmethod
    def load(cls, path: str):
        import joblib
        from pathlib import Path
        data = joblib.load(path)
        instance = cls(target=data["target"], quantiles=data["quantiles"])
        instance.model = data["model"]
        instance.features = data["features"]

        # Dual serialization: bundle dictionary with fallback to separate calibrator joblib
        if "calibrator" in data and data["calibrator"] is not None:
            from nfl_odds.models.calibration import ProbabilityCalibrator
            if isinstance(data["calibrator"], dict):
                instance.calibrator = ProbabilityCalibrator.from_dict(data["calibrator"])
            elif isinstance(data["calibrator"], ProbabilityCalibrator):
                instance.calibrator = data["calibrator"]
        else:
            cal_candidates = [
                Path(path).parent / f"{instance.target}_calibrator.joblib",
                Path("data") / f"{instance.target}_calibrator.joblib",
            ]
            for cal_path in cal_candidates:
                if cal_path.exists():
                    from nfl_odds.models.calibration import ProbabilityCalibrator
                    cal_data = joblib.load(cal_path)
                    if isinstance(cal_data, dict):
                        instance.calibrator = ProbabilityCalibrator.from_dict(cal_data)
                    elif isinstance(cal_data, ProbabilityCalibrator):
                        instance.calibrator = cal_data
                    break
        return instance

    def predict_distribution(self, df: pl.DataFrame) -> np.ndarray:
        """Returns shape (n_samples, n_quantiles)"""
        X = df.select(self.features).to_numpy()
        return self.model.predict(X)
        
    def get_feature_importances(self) -> Dict[str, float]:
        importances = self.model.feature_importances_
        return {f: float(imp) for f, imp in zip(self.features, importances)}
    def _fit_lognormal_quantiles(self, preds: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Vectorized fitting of Log-Normal parameters (mu, sigma) to predicted quantiles."""
        quantiles = np.array(self.quantiles, dtype=np.float64)
        w_norm = stats.norm.ppf(quantiles)
        # Weights prioritize central quantiles while anchoring tails
        weights = np.array([0.6, 0.8, 1.2, 1.5, 1.2, 0.8, 0.6], dtype=np.float64)
        if len(weights) != len(quantiles):
            weights = np.ones_like(quantiles)
        X = np.column_stack([np.ones_like(w_norm), w_norm])
        W = np.diag(weights)
        M = np.linalg.inv(X.T @ W @ X) @ (X.T @ W)

        log_q = np.log(np.maximum(0.5, preds))
        params = log_q @ M.T
        mus = params[:, 0]
        sigmas = np.maximum(0.10, params[:, 1])
        return mus, sigmas

    def probability_both_sides(
        self,
        df: pl.DataFrame,
        lines: np.ndarray,
        distribution: str = "lognormal",
        calibrate: bool = True,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Calculate P(Y > line) and P(Y <= line) using parametric asymmetric Log-Normal or linear interpolation.

        If calibrate=True and calibrator is side-aware, applies independent directional calibration
        for OVER and UNDER.
        """
        preds = self.predict_distribution(df)
        lines_arr = np.asarray(lines, dtype=np.float64)

        if distribution == "lognormal":
            mus, sigmas = self._fit_lognormal_quantiles(preds)
            z = (np.log(np.maximum(0.1, lines_arr)) - mus) / sigmas
            raw_prob_under = stats.norm.cdf(z)
            raw_prob_over = 1.0 - raw_prob_under
        else:
            # Piecewise linear empirical CDF interpolation (legacy fallback)
            probs_over = []
            for i, row_quantiles in enumerate(preds):
                line = lines_arr[i]
                row_quantiles = np.sort(row_quantiles)
                low_pad = min(0.0, float(row_quantiles[0]) - 5.0)
                high_pad = max(float(row_quantiles[-1]) * 1.5, float(row_quantiles[-1]) + 10.0)
                x = np.concatenate(([low_pad], row_quantiles, [high_pad]))
                x = np.sort(x)
                y = np.concatenate(([0.0], self.quantiles, [1.0]))

                dx = np.diff(x)
                if np.any(dx <= 0):
                    x = x + np.linspace(0, 1e-4, len(x))

                interp_cdf = interpolate.interp1d(x, y, kind="linear", bounds_error=False, fill_value=(0.0, 1.0))
                prob_under = float(interp_cdf(line))
                probs_over.append(1.0 - prob_under)

            raw_prob_over = np.array(probs_over, dtype=np.float64)
            raw_prob_under = 1.0 - raw_prob_over

        raw_prob_over = np.clip(raw_prob_over, 0.0001, 0.9999)
        raw_prob_under = np.clip(raw_prob_under, 0.0001, 0.9999)

        if calibrate and self.calibrator is not None:
            if getattr(self.calibrator, "is_side_aware", False):
                cal_over = self.calibrator.calibrate(raw_prob_over, side="over")
                cal_under = self.calibrator.calibrate(raw_prob_under, side="under")
                return np.asarray(cal_over, dtype=np.float64), np.asarray(cal_under, dtype=np.float64)
            else:
                cal_over = self.calibrator.calibrate(raw_prob_over)
                return np.asarray(cal_over, dtype=np.float64), np.asarray(1.0 - cal_over, dtype=np.float64)

        return raw_prob_over, raw_prob_under

    def probability_over_line(
        self,
        df: pl.DataFrame,
        lines: np.ndarray,
        distribution: str = "lognormal",
        calibrate: bool = True,
        side: str = "over",
    ) -> np.ndarray:
        """Calculate P(Y > line) (or P(Y <= line) if side='under') for each sample."""
        p_over, p_under = self.probability_both_sides(df, lines, distribution=distribution, calibrate=calibrate)
        if str(side).lower().strip() == "under":
            return p_under
        return p_over

def split_temporal(df: pl.DataFrame, test_years: List[int]) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Temporal split based on season."""
    train_df = df.filter(~pl.col("season").is_in(test_years))
    test_df = df.filter(pl.col("season").is_in(test_years))
    return train_df, test_df
