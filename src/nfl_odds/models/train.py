import xgboost as xgb
import polars as pl
import numpy as np
from typing import List, Tuple, Dict
from scipy import interpolate

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
        joblib.dump({"model": self.model, "features": self.features, "quantiles": self.quantiles, "target": self.target}, path)
        
    @classmethod
    def load(cls, path: str):
        import joblib
        data = joblib.load(path)
        instance = cls(target=data["target"], quantiles=data["quantiles"])
        instance.model = data["model"]
        instance.features = data["features"]
        return instance

    def predict_distribution(self, df: pl.DataFrame) -> np.ndarray:
        """Returns shape (n_samples, n_quantiles)"""
        X = df.select(self.features).to_numpy()
        return self.model.predict(X)
        
    def get_feature_importances(self) -> Dict[str, float]:
        importances = self.model.feature_importances_
        return {f: float(imp) for f, imp in zip(self.features, importances)}
        
    def probability_over_line(self, df: pl.DataFrame, lines: np.ndarray) -> np.ndarray:
        """Calculate P(Y > line) for each sample."""
        preds = self.predict_distribution(df)
        probs = []
        
        for i, row_quantiles in enumerate(preds):
            line = lines[i]
            # Ensure monotonicity
            row_quantiles = np.sort(row_quantiles)
            # Create CDF empirical function
            # x = quantiles predicted
            # y = cumulative probabilities (the self.quantiles array)
            # To estimate P(Y > line), we interpolate
            
            # Pad with 0 at the low end and something high at the high end
            x = np.concatenate(([0], row_quantiles, [row_quantiles[-1] * 1.5 + 10]))
            y = np.concatenate(([0.0], self.quantiles, [1.0]))
            
            # Ensure x is strictly increasing for interpolation (add tiny noise if flat)
            dx = np.diff(x)
            if np.any(dx <= 0):
                x = x + np.linspace(0, 1e-4, len(x))
            
            interp_cdf = interpolate.interp1d(x, y, kind='linear', bounds_error=False, fill_value=(0.0, 1.0))
            
            prob_under = interp_cdf(line)
            prob_over = 1.0 - prob_under
            probs.append(prob_over)
            
        return np.array(probs)

def split_temporal(df: pl.DataFrame, test_years: List[int]) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Temporal split based on season."""
    train_df = df.filter(~pl.col("season").is_in(test_years))
    test_df = df.filter(pl.col("season").is_in(test_years))
    return train_df, test_df
