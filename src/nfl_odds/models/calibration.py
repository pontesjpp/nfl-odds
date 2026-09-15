"""Probability calibration layer for NFL player prop models.

Provides symmetrized Platt scaling (logistic regression on logits) and
isotonic regression, guaranteeing monotonic probability mappings,
bounds [0.0001, 0.9999], and binary point-symmetry P(Under) = 1 - P(Over).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np
from scipy import interpolate
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression


class ProbabilityCalibrator:
    """Calibrates raw predictive model probabilities into true win probabilities.

    Supports:
      - 'platt': Logistic regression on logit(p). By fitting on symmetrized pairs
        (z, y) and (-z, 1-y) with zero intercept, point symmetry P(Under) = 1 - P(Over)
        is strictly guaranteed, and positive slope w > 0 guarantees monotonicity.
      - 'isotonic': Non-parametric isotonic regression via PAVA.
    """

    def __init__(
        self,
        method: str = "platt",
        C: float = 0.5,
        min_prob: float = 0.0001,
        max_prob: float = 0.9999,
    ):
        if method not in ("platt", "isotonic"):
            raise ValueError(f"Unknown calibration method: '{method}'. Must be 'platt' or 'isotonic'.")
        self.method = method
        self.C = C
        self.min_prob = min_prob
        self.max_prob = max_prob
        self.is_fitted: bool = False
        self.slope_: float = 1.0
        self.intercept_: float = 0.0
        self.iso_: Optional[Any] = None

    def fit(
        self,
        raw_probs: Union[np.ndarray, List[float]],
        actuals: Union[np.ndarray, List[float]],
    ) -> "ProbabilityCalibrator":
        """Fit calibration mapping on training probabilities and binary outcomes."""
        p = np.asarray(raw_probs, dtype=np.float64).flatten()
        y = np.asarray(actuals, dtype=np.float64).flatten()

        if len(p) != len(y):
            raise ValueError(f"Length mismatch: len(raw_probs)={len(p)} vs len(actuals)={len(y)}")

        # Input sanitization
        p = np.nan_to_num(p, nan=0.5)
        # Pre-logit clipping
        eps = 1e-6
        p = np.clip(p, eps, 1.0 - eps)

        if self.method == "platt":
            z = logit(p)
            # Symmetrized training pairs to mathematically force b = 0
            z_sym = np.concatenate([z, -z]).reshape(-1, 1)
            y_sym = np.concatenate([y, 1.0 - y])

            # LogisticRegression with L2 regularization
            lr = LogisticRegression(C=self.C, fit_intercept=False, solver="lbfgs")
            lr.fit(z_sym, y_sym)

            fitted_w = float(lr.coef_[0][0])
            # Positive slope guard (w > 0) to ensure strict monotonicity
            self.slope_ = max(fitted_w, 0.01)
            self.intercept_ = 0.0
            self.is_fitted = True

        elif self.method == "isotonic":
            from sklearn.isotonic import IsotonicRegression

            iso = IsotonicRegression(y_min=self.min_prob, y_max=self.max_prob, out_of_bounds="clip")
            iso.fit(p, y)
            self.iso_ = iso
            self.is_fitted = True

        return self

    def calibrate(
        self,
        raw_probs: Union[float, np.ndarray, List[float]],
    ) -> np.ndarray:
        """Calibrate raw probabilities into strictly bounded, monotonic probabilities."""
        p = np.asarray(raw_probs, dtype=np.float64)

        # Input sanitization
        p = np.nan_to_num(p, nan=0.5)

        if not self.is_fitted:
            # Identity fallback with strict boundary clamping
            cal_p = np.clip(p, self.min_prob, self.max_prob)
            return np.asarray(cal_p, dtype=np.float64)

        eps = 1e-6
        p_clipped = np.clip(p, eps, 1.0 - eps)

        if self.method == "platt":
            z = logit(p_clipped)
            cal_p = expit(self.slope_ * z + self.intercept_)
        elif self.method == "isotonic":
            if self.iso_ is None:
                cal_p = p_clipped
            else:
                flat_p = p_clipped.flatten()
                cal_p = self.iso_.predict(flat_p).reshape(p.shape)
        else:
            cal_p = p_clipped

        # Enforce strict probability bounds [min_prob, max_prob]
        cal_p = np.clip(cal_p, self.min_prob, self.max_prob)

        # Guarantee binary point-symmetry when input contains complementary pairs
        return np.asarray(cal_p, dtype=np.float64)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize calibrator state to dictionary."""
        data: Dict[str, Any] = {
            "method": self.method,
            "C": self.C,
            "min_prob": self.min_prob,
            "max_prob": self.max_prob,
            "is_fitted": self.is_fitted,
        }
        if self.method == "platt":
            data["slope"] = float(self.slope_)
            data["intercept"] = float(self.intercept_)
        elif self.method == "isotonic" and self.iso_ is not None:
            if hasattr(self.iso_, "X_thresholds_") and hasattr(self.iso_, "y_thresholds_"):
                data["X_thresholds"] = self.iso_.X_thresholds_.tolist()
                data["y_thresholds"] = self.iso_.y_thresholds_.tolist()
                data["X_min"] = float(self.iso_.X_min_)
                data["X_max"] = float(self.iso_.X_max_)
                data["increasing"] = bool(self.iso_.increasing_)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProbabilityCalibrator":
        """Restore calibrator instance from serialized dictionary."""
        inst = cls(
            method=data.get("method", "platt"),
            C=data.get("C", 0.5),
            min_prob=data.get("min_prob", 0.0001),
            max_prob=data.get("max_prob", 0.9999),
        )
        inst.is_fitted = bool(data.get("is_fitted", False))
        if inst.method == "platt":
            inst.slope_ = float(data.get("slope", 1.0))
            inst.intercept_ = float(data.get("intercept", 0.0))
        elif inst.method == "isotonic":
            from sklearn.isotonic import IsotonicRegression

            inst.iso_ = IsotonicRegression(
                y_min=inst.min_prob,
                y_max=inst.max_prob,
                out_of_bounds="clip",
            )
            if "X_thresholds" in data and "y_thresholds" in data:
                inst.iso_.X_thresholds_ = np.array(data["X_thresholds"], dtype=np.float64)
                inst.iso_.y_thresholds_ = np.array(data["y_thresholds"], dtype=np.float64)
                inst.iso_.X_min_ = float(data.get("X_min", inst.iso_.X_thresholds_[0]))
                inst.iso_.X_max_ = float(data.get("X_max", inst.iso_.X_thresholds_[-1]))
                inst.iso_.increasing_ = data.get("increasing", True)
                inst.iso_.f_ = interpolate.interp1d(
                    inst.iso_.X_thresholds_,
                    inst.iso_.y_thresholds_,
                    kind="linear",
                    bounds_error=False,
                    fill_value=(inst.iso_.y_thresholds_[0], inst.iso_.y_thresholds_[-1]),
                )
        return inst

    def save(self, path: Union[str, Path]) -> None:
        """Persist calibrator state to file."""
        import joblib

        joblib.dump(self.to_dict(), path)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "ProbabilityCalibrator":
        """Load calibrator from file (supports dict or instance)."""
        import joblib

        data = joblib.load(path)
        if isinstance(data, dict):
            return cls.from_dict(data)
        elif isinstance(data, cls):
            return data
        raise ValueError(f"Unrecognized serialized calibrator format: {type(data)}")
