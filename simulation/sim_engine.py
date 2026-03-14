# simulation/sim_engine.py
"""
ML-driven simulation engine.
Generates up to 4 forward price scenarios based on:
  - User-defined criteria (direction, risk, confidence threshold, SL/TP method)
  - ML prediction probabilities
  - SMC confluence
  - Indicator confluence

Each scenario is an independent Monte Carlo path seeded by ML probability
and constrained by ATR-based volatility. Scenarios are labelled:
  Bull Case / Base Case / Bear Case / Wildcard

Each scenario also runs a full trade simulation:
  - Detects ML signal entries matching user criteria
  - Places SL and TP
  - Tracks equity curve
  - Reports win rate, RR, max drawdown, profit factor
"""

import numpy as np
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


# ── User criteria dataclass ───────────────────────────────────────────────────

@dataclass
class SimCriteria:
    direction:          str   = "BOTH"      # "LONG", "SHORT", "BOTH"
    risk_pct:           float = 1.0         # risk per trade as % of equity
    min_confidence:     str   = "Medium"    # "High", "Medium", "Low"
    min_probability:    float = 0.60        # minimum ML probability
    require_smc:        bool  = True        # require OB or FVG confirmation
    require_ind:        bool  = True        # require indicator confluence
    sl_method:          str   = "ATR"       # "ATR", "FIXED_PCT", "SWING"
    sl_atr_mult:        float = 1.5         # ATR multiplier for SL
    sl_fixed_pct:       float = 1.0         # fixed SL %
    tp_method:          str   = "RR"        # "RR", "ATR", "FIXED_PCT"
    tp_rr:              float = 2.0         # risk-reward ratio
    tp_atr_mult:        float = 3.0
    tp_fixed_pct:       float = 2.0
    num_candles:        int   = 50          # how many candles to simulate forward
    starting_equity:    float = 10000.0


@dataclass
class SimTrade:
    entry_idx:   int
    entry_price: float
    direction:   str        # "LONG" or "SHORT"
    sl:          float
    tp:          float
    exit_idx:    Optional[int]   = None
    exit_price:  Optional[float] = None
    result:      str             = "OPEN"   # "WIN", "LOSS", "OPEN"
    pnl_pct:     float           = 0.0
    pnl_dollar:  float           = 0.0
    probability: float           = 0.0
    confidence:  str             = "Low"


@dataclass
class SimScenario:
    name:          str
    color:         str
    candles:       List[Dict]    = field(default_factory=list)
    trades:        List[SimTrade] = field(default_factory=list)
    equity_curve:  List[float]   = field(default_factory=list)
    final_equity:  float         = 10000.0
    win_rate:      float         = 0.0
    profit_factor: float         = 0.0
    max_drawdown:  float         = 0.0
    total_trades:  int           = 0
    up_probability: float        = 0.5


# ── Scenario colours ──────────────────────────────────────────────────────────

SCENARIO_COLORS = {
    "Bull Case":  "#00c896",
    "Base Case":  "#4a9eff",
    "Bear Case":  "#ff5252",
    "Wildcard":   "#ffb74d",
}


class SimEngine:
    """
    Generates 1–4 forward simulation scenarios from current market state.
    """

    def __init__(self):
        self._last_scenarios: List[SimScenario] = []

    def run(
        self,
        live_candles:      List[Dict],
        indicator_results: Dict[str, np.ndarray],
        smc_results:       Dict,
        predictor,                           # PredictionEngine instance
        criteria:          SimCriteria,
        n_scenarios:       int = 4,
    ) -> List[SimScenario]:
        """
        Run simulation. Returns list of SimScenario objects.
        """
        if not live_candles or len(live_candles) < 50:
            return []

        last_candle = live_candles[-1]
        close       = float(last_candle["close"])
        atr         = self._get_atr(indicator_results, close)
        prediction  = predictor.get_last()

        # Base UP probability from ML
        base_up_prob = prediction.probability if prediction.ready else 0.5
        if prediction.direction == "DOWN":
            base_up_prob = 1.0 - prediction.probability

        # Define scenario seeds
        scenario_defs = [
            ("Bull Case", "Bull Case",  min(0.95, base_up_prob + 0.15)),
            ("Base Case", "Base Case",  base_up_prob),
            ("Bear Case", "Bear Case",  max(0.05, base_up_prob - 0.15)),
            ("Wildcard",  "Wildcard",   np.random.uniform(0.1, 0.9)),
        ][:n_scenarios]

        scenarios = []
        for name, color_key, up_prob in scenario_defs:
            scenario = self._build_scenario(
                name           = name,
                color          = SCENARIO_COLORS.get(color_key, "#888"),
                live_candles   = live_candles,
                indicator_results = indicator_results,
                smc_results    = smc_results,
                up_prob        = up_prob,
                atr            = atr,
                close          = close,
                criteria       = criteria,
            )
            scenarios.append(scenario)

        self._last_scenarios = scenarios
        return scenarios

    def _build_scenario(
        self,
        name:              str,
        color:             str,
        live_candles:      List[Dict],
        indicator_results: Dict,
        smc_results:       Dict,
        up_prob:           float,
        atr:               float,
        close:             float,
        criteria:          SimCriteria,
    ) -> SimScenario:

        scenario = SimScenario(name=name, color=color, up_probability=up_prob)

        # ── Generate synthetic candles ────────────────────────────────────────
        synth = self._generate_candles(
            start_price = close,
            up_prob     = up_prob,
            atr         = atr,
            n           = criteria.num_candles,
            last_time   = int(live_candles[-1]["time"]),
            timeframe   = self._detect_timeframe(live_candles),
        )
        scenario.candles = synth

        # ── Run trade simulation on synthetic candles ────────────────────────
        trades, equity = self._simulate_trades(
            candles    = synth,
            atr        = atr,
            up_prob    = up_prob,
            criteria   = criteria,
            smc_results = smc_results,
            indicator_results = indicator_results,
        )
        scenario.trades       = trades
        scenario.equity_curve = equity
        scenario.final_equity = equity[-1] if equity else criteria.starting_equity
        scenario.total_trades = len(trades)

        # ── Compute stats ─────────────────────────────────────────────────────
        wins   = [t for t in trades if t.result == "WIN"]
        losses = [t for t in trades if t.result == "LOSS"]

        scenario.win_rate = len(wins) / max(1, len(trades))

        gross_profit = sum(t.pnl_dollar for t in wins)
        gross_loss   = abs(sum(t.pnl_dollar for t in losses))
        scenario.profit_factor = (
            gross_profit / gross_loss if gross_loss > 0 else
            gross_profit if gross_profit > 0 else 0.0
        )

        if equity:
            peak = equity[0]
            max_dd = 0.0
            for eq in equity:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak
                if dd > max_dd:
                    max_dd = dd
            scenario.max_drawdown = max_dd

        return scenario

    def _generate_candles(
        self,
        start_price: float,
        up_prob:     float,
        atr:         float,
        n:           int,
        last_time:   int,
        timeframe:   int,
    ) -> List[Dict]:
        """
        Generate n synthetic OHLCV candles using a biased random walk.
        Drift is set by up_prob. Volatility is ATR-calibrated.
        """
        candles = []
        price   = start_price
        rng     = np.random.default_rng()

        # Drift per candle based on up_prob
        drift = (up_prob - 0.5) * 2 * atr * 0.3

        for i in range(n):
            # Body
            body_size = rng.exponential(atr * 0.5)
            direction = 1 if rng.random() < up_prob else -1
            open_p    = price
            close_p   = price + direction * body_size + drift

            # Wicks
            upper_wick = rng.exponential(atr * 0.2)
            lower_wick = rng.exponential(atr * 0.2)
            high_p     = max(open_p, close_p) + upper_wick
            low_p      = min(open_p, close_p) - lower_wick

            # Clamp to positive prices
            low_p   = max(low_p, price * 0.001)
            close_p = max(close_p, price * 0.001)

            candles.append({
                "time":      last_time + (i + 1) * timeframe,
                "open":      round(open_p,  6),
                "high":      round(high_p,  6),
                "low":       round(low_p,   6),
                "close":     round(close_p, 6),
                "volume":    float(rng.integers(1000, 50000)),
                "synthetic": True,
            })
            price = close_p

        return candles

    def _simulate_trades(
        self,
        candles:           List[Dict],
        atr:               float,
        up_prob:           float,
        criteria:          SimCriteria,
        smc_results:       Dict,
        indicator_results: Dict,
    ) -> tuple:
        """
        Simulate trades on synthetic candles using user criteria.
        Returns (trades, equity_curve).
        """
        trades       = []
        equity       = criteria.starting_equity
        equity_curve = [equity]
        in_trade     = False
        current_trade: Optional[SimTrade] = None
        n            = len(candles)

        # Signal frequency — fire a signal every N candles if conditions met
        signal_every = max(3, n // 12)

        for i, candle in enumerate(candles):
            close = float(candle["close"])
            high  = float(candle["high"])
            low   = float(candle["low"])

            # ── Check open trade exit ─────────────────────────────────────────
            if in_trade and current_trade:
                hit_tp = hit_sl = False

                if current_trade.direction == "LONG":
                    hit_tp = high >= current_trade.tp
                    hit_sl = low  <= current_trade.sl
                else:
                    hit_tp = low  <= current_trade.tp
                    hit_sl = high >= current_trade.sl

                if hit_tp or hit_sl:
                    exit_price = current_trade.tp if hit_tp else current_trade.sl
                    result     = "WIN" if hit_tp else "LOSS"

                    risk_dollar = equity * (criteria.risk_pct / 100)
                    if current_trade.direction == "LONG":
                        pnl_pct = (exit_price - current_trade.entry_price) / current_trade.entry_price
                    else:
                        pnl_pct = (current_trade.entry_price - exit_price) / current_trade.entry_price

                    pnl_dollar = risk_dollar * (
                        criteria.tp_rr if result == "WIN" else -1.0
                    )

                    current_trade.exit_idx   = i
                    current_trade.exit_price = exit_price
                    current_trade.result     = result
                    current_trade.pnl_pct    = pnl_pct
                    current_trade.pnl_dollar = pnl_dollar

                    equity += pnl_dollar
                    equity  = max(equity, 0.01)
                    in_trade = False
                    current_trade = None

            equity_curve.append(round(equity, 2))

            # ── Check for new signal ──────────────────────────────────────────
            if not in_trade and i % signal_every == 0 and i < n - 5:

                # Determine direction based on ML probability at this point
                candle_up_prob = up_prob * (0.97 ** i)

                if candle_up_prob > criteria.min_probability:
                    signal_dir = "LONG"
                    signal_conf = self._prob_to_confidence(candle_up_prob)
                elif (1 - candle_up_prob) > criteria.min_probability:
                    signal_dir = "SHORT"
                    signal_conf = self._prob_to_confidence(1 - candle_up_prob)
                else:
                    continue

                # Apply user criteria filters
                if criteria.direction == "LONG"  and signal_dir != "LONG":  continue
                if criteria.direction == "SHORT" and signal_dir != "SHORT": continue
                if not self._meets_confidence(signal_conf, criteria.min_confidence): continue

                # SMC filter (simplified — check if any OB/FVG in smc_results)
                if criteria.require_smc:
                    has_smc = bool(
                        smc_results.get("order_blocks") or
                        smc_results.get("fvgs")
                    )
                    if not has_smc:
                        continue

                # Build trade
                entry = close
                sl, tp = self._calc_sl_tp(
                    entry, signal_dir, atr, criteria, candles, i
                )

                t = SimTrade(
                    entry_idx   = i,
                    entry_price = entry,
                    direction   = signal_dir,
                    sl          = sl,
                    tp          = tp,
                    probability = candle_up_prob if signal_dir == "LONG" else 1 - candle_up_prob,
                    confidence  = signal_conf,
                )
                trades.append(t)
                current_trade = t
                in_trade      = True

        # Close any open trade at end of simulation
        if in_trade and current_trade:
            last_close = float(candles[-1]["close"])
            current_trade.exit_idx   = len(candles) - 1
            current_trade.exit_price = last_close
            current_trade.result     = "OPEN"

        return trades, equity_curve

    def _calc_sl_tp(
        self,
        entry:     float,
        direction: str,
        atr:       float,
        criteria:  SimCriteria,
        candles:   List[Dict],
        idx:       int,
    ) -> tuple:
        """Calculate SL and TP prices."""
        if criteria.sl_method == "ATR":
            sl_dist = atr * criteria.sl_atr_mult
        elif criteria.sl_method == "FIXED_PCT":
            sl_dist = entry * (criteria.sl_fixed_pct / 100)
        else:  # SWING
            lookback = candles[max(0, idx-10):idx+1]
            if direction == "LONG":
                sl_dist = entry - min(float(c["low"]) for c in lookback)
            else:
                sl_dist = max(float(c["high"]) for c in lookback) - entry
            sl_dist = max(sl_dist, atr * 0.5)

        if criteria.tp_method == "RR":
            tp_dist = sl_dist * criteria.tp_rr
        elif criteria.tp_method == "ATR":
            tp_dist = atr * criteria.tp_atr_mult
        else:
            tp_dist = entry * (criteria.tp_fixed_pct / 100)

        if direction == "LONG":
            return (entry - sl_dist, entry + tp_dist)
        else:
            return (entry + sl_dist, entry - tp_dist)

    def _get_atr(self, indicator_results: Dict, close: float) -> float:
        atr_arr = indicator_results.get("ATR", np.array([]))
        if len(atr_arr) > 0:
            val = float(atr_arr[-1])
            if not np.isnan(val) and val > 0:
                return val
        return close * 0.002

    def _detect_timeframe(self, candles: List[Dict]) -> int:
        """Detect candle interval in seconds from timestamps."""
        if len(candles) < 2:
            return 3600
        diff = int(candles[-1]["time"]) - int(candles[-2]["time"])
        return max(60, diff)

    def _prob_to_confidence(self, prob: float) -> str:
        if prob >= 0.70: return "High"
        if prob >= 0.58: return "Medium"
        return "Low"

    def _meets_confidence(self, signal_conf: str, min_conf: str) -> bool:
        order = {"Low": 0, "Medium": 1, "High": 2}
        return order.get(signal_conf, 0) >= order.get(min_conf, 0)
