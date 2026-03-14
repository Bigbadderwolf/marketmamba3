# ml/xgb_model.py
"""
XGBoost classifier wrapper.
Trained on 42-feature vectors to predict UP/DOWN direction.
Outputs probability scores (0-1) for directional bias.
"""

import os
import pickle
import logging
import numpy as np
from typing import Optional, Tuple

log = logging.getLogger(__name__)


class XGBModel:
    """
    Wraps XGBoost classifier with training, prediction and persistence.
    One instance per asset symbol.
    """

    def __init__(self, symbol: str):
        self.symbol    = symbol.lower().replace("/", "")
        self.model     = None
        self.is_trained = False
        self.train_accuracy = 0.0
        self.feature_importances: Optional[np.ndarray] = None
        self._model_path = self._get_path()

    def _get_path(self) -> str:
        from config.constants import MODELS_DIR
        return os.path.join(MODELS_DIR, f"xgb_{self.symbol}.pkl")

    def train(self, X: np.ndarray, y: np.ndarray) -> float:
        """
        Train XGBoost classifier on (X, y).
        Returns validation accuracy.
        """
        if len(X) < 50:
            log.warning("XGB %s: too few samples (%d), skipping", self.symbol, len(X))
            return 0.0

        try:
            from xgboost import XGBClassifier
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import accuracy_score

            # Split train/val
            X_tr, X_val, y_tr, y_val = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )

            scale_pos_weight = float(np.sum(y_tr == 0)) / max(1, float(np.sum(y_tr == 1)))

            self.model = XGBClassifier(
                n_estimators        = 300,
                max_depth           = 6,
                learning_rate       = 0.05,
                subsample           = 0.8,
                colsample_bytree    = 0.8,
                scale_pos_weight    = scale_pos_weight,
                use_label_encoder   = False,
                eval_metric         = "logloss",
                random_state        = 42,
                n_jobs              = -1,
                verbosity           = 0,
            )

            self.model.fit(
                X_tr, y_tr,
                eval_set   = [(X_val, y_val)],
                verbose    = False,
            )

            y_pred = self.model.predict(X_val)
            self.train_accuracy = float(accuracy_score(y_val, y_pred))
            self.feature_importances = self.model.feature_importances_
            self.is_trained = True

            log.info("XGB %s trained: acc=%.3f samples=%d",
                     self.symbol, self.train_accuracy, len(X))
            return self.train_accuracy

        except Exception as e:
            log.error("XGB training failed for %s: %s", self.symbol, e)
            return 0.0

    def predict_proba(self, features: np.ndarray) -> Tuple[float, float]:
        """
        Predict probability of DOWN (0) and UP (1).
        Returns (prob_down, prob_up) tuple.
        """
        if not self.is_trained or self.model is None:
            return (0.5, 0.5)

        try:
            x = features.reshape(1, -1)
            proba = self.model.predict_proba(x)[0]
            return (float(proba[0]), float(proba[1]))
        except Exception as e:
            log.error("XGB predict failed: %s", e)
            return (0.5, 0.5)

    def incremental_update(self, X: np.ndarray, y: np.ndarray):
        """
        Lightweight incremental update using the last N samples.
        XGBoost doesn't support true online learning so we retrain
        on a rolling window of recent data.
        """
        if len(X) >= 50:
            self.train(X[-500:], y[-500:])

    def save(self):
        """Persist model to disk."""
        if self.model is None:
            return
        try:
            with open(self._model_path, "wb") as f:
                pickle.dump({
                    "model":              self.model,
                    "is_trained":         self.is_trained,
                    "train_accuracy":     self.train_accuracy,
                    "feature_importances": self.feature_importances,
                }, f)
            log.info("XGB saved: %s", self._model_path)
        except Exception as e:
            log.error("XGB save failed: %s", e)

    def load(self) -> bool:
        """Load model from disk. Returns True if successful."""
        if not os.path.exists(self._model_path):
            return False
        try:
            with open(self._model_path, "rb") as f:
                data = pickle.load(f)
            self.model               = data["model"]
            self.is_trained          = data["is_trained"]
            self.train_accuracy      = data.get("train_accuracy", 0.0)
            self.feature_importances = data.get("feature_importances")
            log.info("XGB loaded: %s (acc=%.3f)", self.symbol, self.train_accuracy)
            return True
        except Exception as e:
            log.error("XGB load failed: %s", e)
            return False
