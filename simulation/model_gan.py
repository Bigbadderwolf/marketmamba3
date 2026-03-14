# simulation/model_gan.py
"""
GAN-Generated simulation model.
Trains a lightweight GAN on normalised OHLCV sequences.
Generator: noise vector → sequence of normalised candle features
Discriminator: sequence → real/fake probability

If TensorFlow unavailable, falls back to a parametric model
that mimics GAN-like variety using learned distribution mixing.

Training: ~5-10 min on i5/8GB (done once, saved to disk).
Inference: instant after training.
"""

import os
import logging
import numpy as np
from typing import List, Dict, Optional
from simulation.base_model import BaseSimModel, GeneratedPath

log = logging.getLogger(__name__)

SEQ_LEN    = 32    # candles per sequence
NOISE_DIM  = 64
N_FEATURES = 5     # open_ret, high_ret, low_ret, close_ret, vol_norm


def _tf_available() -> bool:
    try:
        import tensorflow as tf  # noqa
        return True
    except ImportError:
        return False


class GANModel(BaseSimModel):

    MODEL_ID   = "gan"
    MODEL_NAME = "GAN-Generated"
    COLOR      = "#ff9800"

    def __init__(self):
        super().__init__()
        self._generator    = None
        self._discriminator = None
        self._use_tf       = _tf_available()
        self._mean_ret     = 0.0
        self._std_ret      = 0.001
        self._mean_vol     = 10000.0
        self._std_vol      = 5000.0
        self._atr_val      = 0.0
        # Learned distribution mixing parameters (fallback)
        self._mixture_weights = np.array([0.4, 0.4, 0.2])
        self._mixture_params  = [
            (0.0005, 0.008),   # mild up-trend
            (-0.0003, 0.009),  # mild down-trend
            (0.0000, 0.015),   # volatile ranging
        ]
        self._model_path = self._get_path()

    def _get_path(self) -> str:
        from config.constants import MODELS_DIR
        return os.path.join(MODELS_DIR, "gan_generator.h5")

    def fit(self, candles: List[Dict]) -> None:
        if len(candles) < SEQ_LEN * 4:
            log.warning("GAN: insufficient candles (%d), using fallback", len(candles))
            self._fit_fallback(candles)
            return

        self._atr_val  = self._atr(candles)
        returns        = self._extract_returns(candles)
        self._mean_ret = float(np.mean(returns))
        self._std_ret  = max(float(np.std(returns)), 1e-6)
        volumes        = [float(c.get("volume", 10000)) for c in candles]
        self._mean_vol = float(np.mean(volumes))
        self._std_vol  = max(float(np.std(volumes)), 1.0)

        if self._use_tf:
            # Try to load saved generator first
            if os.path.exists(self._model_path):
                try:
                    from tensorflow.keras.models import load_model
                    self._generator = load_model(self._model_path)
                    self._fitted    = True
                    log.info("GAN generator loaded from disk")
                    return
                except Exception as e:
                    log.warning("GAN load failed: %s — retraining", e)

            # Build + train
            self._train_gan(candles)
        else:
            log.info("GAN: TensorFlow not available, using parametric fallback")
            self._fit_fallback(candles)

        self._fitted = True

    def _fit_fallback(self, candles: List[Dict]) -> None:
        """Fit mixture distribution without TensorFlow."""
        if len(candles) < 10:
            return
        returns = self._extract_returns(candles)
        self._mean_ret = float(np.mean(returns))
        self._std_ret  = max(float(np.std(returns)), 1e-6)
        self._atr_val  = self._atr(candles)
        # Fit 3-component mixture: uptrend, downtrend, ranging
        threshold = self._std_ret * 0.5
        up_rets   = returns[returns >  threshold]
        dn_rets   = returns[returns < -threshold]
        rn_rets   = returns[np.abs(returns) <= threshold]
        def _params(r): return (float(np.mean(r)), max(float(np.std(r)), 1e-6))
        self._mixture_params = [
            _params(up_rets) if len(up_rets) > 2 else ( 0.0005, 0.008),
            _params(dn_rets) if len(dn_rets) > 2 else (-0.0005, 0.008),
            _params(rn_rets) if len(rn_rets) > 2 else ( 0.0000, 0.015),
        ]
        n_up = max(1, len(up_rets))
        n_dn = max(1, len(dn_rets))
        n_rn = max(1, len(rn_rets))
        total = n_up + n_dn + n_rn
        self._mixture_weights = np.array([n_up, n_dn, n_rn], dtype=float) / total
        volumes = [float(c.get("volume", 10000)) for c in candles]
        self._mean_vol = float(np.mean(volumes))
        self._std_vol  = max(float(np.std(volumes)), 1.0)

    def _train_gan(self, candles: List[Dict]) -> None:
        """Train lightweight GAN using TensorFlow/Keras."""
        try:
            import tensorflow as tf
            from tensorflow.keras import layers, Model, optimizers
            import threading

            # Prepare training data
            X = self._prepare_sequences(candles)
            if X is None or len(X) < 10:
                self._fit_fallback(candles)
                return

            # Generator
            noise_in  = layers.Input(shape=(NOISE_DIM,))
            x = layers.Dense(128, activation="relu")(noise_in)
            x = layers.Dense(256, activation="relu")(x)
            x = layers.Reshape((SEQ_LEN, N_FEATURES))(
                layers.Dense(SEQ_LEN * N_FEATURES)(x)
            )
            generator = Model(noise_in, x, name="generator")

            # Discriminator
            seq_in = layers.Input(shape=(SEQ_LEN, N_FEATURES))
            y = layers.LSTM(64)(seq_in)
            y = layers.Dense(32, activation="relu")(y)
            y = layers.Dense(1, activation="sigmoid")(y)
            discriminator = Model(seq_in, y, name="discriminator")
            discriminator.compile(
                optimizer=optimizers.Adam(0.0002),
                loss="binary_crossentropy"
            )

            # Train in background — won't block UI
            def _train_bg():
                try:
                    d_opt = optimizers.Adam(0.0002)
                    g_opt = optimizers.Adam(0.0002)
                    bce   = tf.keras.losses.BinaryCrossentropy()
                    batch = min(32, len(X))

                    for epoch in range(50):
                        idx  = np.random.choice(len(X), batch, replace=False)
                        real = tf.constant(X[idx], dtype=tf.float32)
                        noise = tf.random.normal([batch, NOISE_DIM])
                        fake  = generator(noise, training=False)

                        # Train discriminator
                        with tf.GradientTape() as tape:
                            real_out = discriminator(real,  training=True)
                            fake_out = discriminator(fake,  training=True)
                            d_loss   = (bce(tf.ones_like(real_out), real_out) +
                                        bce(tf.zeros_like(fake_out), fake_out))
                        grads = tape.gradient(d_loss, discriminator.trainable_variables)
                        d_opt.apply_gradients(zip(grads, discriminator.trainable_variables))

                        # Train generator
                        noise2 = tf.random.normal([batch, NOISE_DIM])
                        with tf.GradientTape() as tape:
                            gen_out = generator(noise2, training=True)
                            g_loss  = bce(tf.ones_like(discriminator(gen_out)), discriminator(gen_out))
                        grads2 = tape.gradient(g_loss, generator.trainable_variables)
                        g_opt.apply_gradients(zip(grads2, generator.trainable_variables))

                    generator.save(self._model_path)
                    self._generator = generator
                    log.info("GAN training complete")
                except Exception as e:
                    log.error("GAN training error: %s", e)
                    self._fit_fallback(candles)

            threading.Thread(target=_train_bg, daemon=True).start()
            # Use fallback until training completes
            self._fit_fallback(candles)

        except Exception as e:
            log.error("GAN setup failed: %s", e)
            self._fit_fallback(candles)

    def _prepare_sequences(self, candles: List[Dict]) -> Optional[np.ndarray]:
        """Convert candles to normalised feature sequences."""
        try:
            closes  = np.array([float(c["close"])  for c in candles])
            highs   = np.array([float(c["high"])   for c in candles])
            lows    = np.array([float(c["low"])    for c in candles])
            opens   = np.array([float(c["open"])   for c in candles])
            volumes = np.array([float(c.get("volume", 10000)) for c in candles])

            ret_c = np.diff(np.log(np.maximum(closes, 1e-10)))
            ret_h = (highs[1:] - closes[:-1]) / np.maximum(closes[:-1], 1e-10)
            ret_l = (lows[1:]  - closes[:-1]) / np.maximum(closes[:-1], 1e-10)
            ret_o = (opens[1:] - closes[:-1]) / np.maximum(closes[:-1], 1e-10)
            vol_n = (volumes[1:] - np.mean(volumes)) / (np.std(volumes) + 1e-10)
            vol_n = np.clip(vol_n, -3, 3)

            features = np.stack([ret_o, ret_h, ret_l, ret_c, vol_n], axis=1)
            features = np.clip(features, -0.1, 0.1)

            n_seq = len(features) - SEQ_LEN + 1
            if n_seq < 10:
                return None
            seqs = np.array([features[i:i+SEQ_LEN] for i in range(n_seq)],
                            dtype=np.float32)
            return seqs
        except Exception as e:
            log.error("GAN sequence prep failed: %s", e)
            return None

    def generate(self, n_candles: int, start_price: float,
                 last_time: int, timeframe_secs: int) -> GeneratedPath:

        if not self._fitted or start_price <= 0:
            return self._fallback_path(n_candles, start_price, last_time, timeframe_secs)

        rng    = np.random.default_rng()
        price  = start_price
        candles = []
        source  = "gan" if (self._use_tf and self._generator is not None) else "mixture"

        # Generate returns
        all_returns = []
        if source == "gan":
            try:
                import tensorflow as tf
                n_seqs = (n_candles // SEQ_LEN) + 2
                noise  = tf.random.normal([n_seqs, NOISE_DIM])
                seqs   = self._generator(noise, training=False).numpy()
                # Extract close returns (index 3)
                flat_rets = seqs[:, :, 3].flatten()[:n_candles]
                all_returns = flat_rets.tolist()
            except Exception as e:
                log.warning("GAN inference failed: %s — using fallback", e)
                source = "mixture"

        if source == "mixture":
            for _ in range(n_candles):
                comp = int(rng.choice(3, p=self._mixture_weights))
                mu, sigma = self._mixture_params[comp]
                all_returns.append(float(rng.normal(mu, sigma)))

        # Build candles from returns
        for i, ret in enumerate(all_returns[:n_candles]):
            ret    = np.clip(ret, -0.08, 0.08)
            open_  = price
            close  = price * np.exp(ret)
            close  = max(close, price * 0.001)

            atr    = self._atr_val if self._atr_val > 0 else price * 0.002
            high   = max(open_, close) + rng.exponential(atr * 0.2)
            low    = min(open_, close) - rng.exponential(atr * 0.18)
            low    = max(low, close * 0.0001)

            vol    = max(100.0, self._mean_vol + rng.normal(0, self._std_vol * 0.5))
            ts     = last_time + (i + 1) * timeframe_secs
            candles.append(self._make_candle(open_, high, low, close, vol, ts))
            price = close

        return GeneratedPath(
            candles    = candles,
            model_name = self.MODEL_NAME,
            model_id   = self.MODEL_ID,
            color      = self.COLOR,
            confidence_bands = None,
            metadata   = {"source": source, "tf_available": self._use_tf},
        )

    def _fallback_path(self, n, price, t0, tf) -> GeneratedPath:
        candles = []
        for i in range(n):
            candles.append(self._make_candle(price, price, price, price, 0,
                                             t0 + (i + 1) * tf))
        return GeneratedPath(candles=candles, model_name=self.MODEL_NAME,
                             model_id=self.MODEL_ID, color=self.COLOR,
                             confidence_bands=None)
