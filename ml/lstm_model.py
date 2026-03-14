# ml/lstm_model.py
"""
LSTM model wrapper for sequence-based prediction.
Uses last 30 candles of 42-feature vectors as input sequence.
Outputs probability of UP direction.

Keras/TensorFlow is optional — if not installed, LSTM is silently skipped
and XGBoost carries the prediction alone.
"""

import os
import logging
import numpy as np
from typing import Optional, Tuple

log = logging.getLogger(__name__)

SEQUENCE_LEN = 30   # Number of candles to look back


def _keras_available() -> bool:
    try:
        import tensorflow as tf  # noqa
        return True
    except ImportError:
        try:
            import keras  # noqa
            return True
        except ImportError:
            return False


class LSTMModel:
    """
    LSTM sequence classifier.
    Input:  (SEQUENCE_LEN, 42) feature matrix
    Output: probability of UP direction
    """

    def __init__(self, symbol: str):
        self.symbol     = symbol.lower().replace("/", "")
        self.model      = None
        self.is_trained = False
        self.train_accuracy = 0.0
        self._available = _keras_available()
        self._model_path = self._get_path()

        if not self._available:
            log.warning("TensorFlow/Keras not available — LSTM disabled for %s", symbol)

    def _get_path(self) -> str:
        from config.constants import MODELS_DIR
        return os.path.join(MODELS_DIR, f"lstm_{self.symbol}.h5")

    def _build_model(self, n_features: int = 42):
        """Build LSTM architecture."""
        try:
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import (
                LSTM, Dense, Dropout, BatchNormalization
            )
            from tensorflow.keras.optimizers import Adam
            from tensorflow.keras.callbacks import EarlyStopping

            model = Sequential([
                LSTM(64, input_shape=(SEQUENCE_LEN, n_features),
                     return_sequences=True),
                Dropout(0.2),
                BatchNormalization(),
                LSTM(32, return_sequences=False),
                Dropout(0.2),
                Dense(16, activation="relu"),
                Dense(1,  activation="sigmoid"),
            ])

            model.compile(
                optimizer = Adam(learning_rate=0.001),
                loss      = "binary_crossentropy",
                metrics   = ["accuracy"],
            )
            return model

        except Exception as e:
            log.error("LSTM build failed: %s", e)
            return None

    def _make_sequences(self, X: np.ndarray, y: np.ndarray):
        """Convert flat feature array to (N, SEQUENCE_LEN, 42) sequences."""
        Xs, ys = [], []
        for i in range(SEQUENCE_LEN, len(X)):
            Xs.append(X[i - SEQUENCE_LEN:i])
            ys.append(y[i])
        if not Xs:
            return np.array([]), np.array([])
        return np.array(Xs, dtype=np.float32), np.array(ys, dtype=np.float32)

    def train(self, X: np.ndarray, y: np.ndarray) -> float:
        """Train LSTM on feature sequences. Returns val accuracy."""
        if not self._available:
            return 0.0
        if len(X) < SEQUENCE_LEN + 30:
            log.warning("LSTM %s: too few samples", self.symbol)
            return 0.0

        try:
            from tensorflow.keras.callbacks import EarlyStopping
            from sklearn.model_selection import train_test_split

            X_seq, y_seq = self._make_sequences(X, y)
            if len(X_seq) < 20:
                return 0.0

            X_tr, X_val, y_tr, y_val = train_test_split(
                X_seq, y_seq, test_size=0.2, random_state=42
            )

            self.model = self._build_model(X.shape[1])
            if self.model is None:
                return 0.0

            es = EarlyStopping(
                monitor   = "val_loss",
                patience  = 5,
                restore_best_weights = True,
                verbose   = 0,
            )

            self.model.fit(
                X_tr, y_tr,
                validation_data = (X_val, y_val),
                epochs          = 30,
                batch_size      = 32,
                callbacks       = [es],
                verbose         = 0,
            )

            _, acc = self.model.evaluate(X_val, y_val, verbose=0)
            self.train_accuracy = float(acc)
            self.is_trained = True

            log.info("LSTM %s trained: acc=%.3f", self.symbol, self.train_accuracy)
            return self.train_accuracy

        except Exception as e:
            log.error("LSTM training failed for %s: %s", self.symbol, e)
            return 0.0

    def predict_proba(self, feature_sequence: np.ndarray) -> float:
        """
        Predict probability of UP direction.
        feature_sequence: (SEQUENCE_LEN, 42) array
        Returns float 0-1.
        """
        if not self.is_trained or self.model is None:
            return 0.5
        try:
            x    = feature_sequence.reshape(1, SEQUENCE_LEN, -1)
            prob = float(self.model.predict(x, verbose=0)[0][0])
            return prob
        except Exception as e:
            log.error("LSTM predict failed: %s", e)
            return 0.5

    def save(self):
        if self.model is None:
            return
        try:
            self.model.save(self._model_path)
            log.info("LSTM saved: %s", self._model_path)
        except Exception as e:
            log.error("LSTM save failed: %s", e)

    def load(self) -> bool:
        if not self._available or not os.path.exists(self._model_path):
            return False
        try:
            from tensorflow.keras.models import load_model
            self.model       = load_model(self._model_path)
            self.is_trained  = True
            log.info("LSTM loaded: %s", self.symbol)
            return True
        except Exception as e:
            log.error("LSTM load failed: %s", e)
            return False
