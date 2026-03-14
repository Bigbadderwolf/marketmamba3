# smc/detector.py
"""
Smart Money Concepts (SMC) Detection Engine.
Detects all SMC features from raw candle data:
  - Order Blocks (bullish and bearish)
  - Fair Value Gaps (FVGs)
  - Break of Structure (BOS) and Change of Character (CHoCH)
  - Liquidity Sweeps and Stop Hunts

All detected features are returned as structured dicts
ready for chart rendering (Phase 6) and ML features (Phase 4).
"""

import numpy as np
from typing import List, Dict, Optional
import logging

log = logging.getLogger(__name__)


class SMCDetector:
    """
    Master SMC detection pipeline.
    Call detect() with candle list to get all SMC features.
    """

    def __init__(self, swing_lookback: int = 5):
        """
        swing_lookback: number of candles each side to confirm a swing high/low.
        Higher = fewer but stronger swings detected.
        """
        self.swing_lookback = swing_lookback
        self.result: Dict = {}

    def detect(self, candles: List[Dict]) -> Dict:
        """
        Run full SMC detection pipeline.
        Returns dict with keys: order_blocks, fvgs, structure, liquidity
        """
        if len(candles) < self.swing_lookback * 2 + 2:
            return {
                "order_blocks": [],
                "fvgs":         [],
                "structure":    [],
                "liquidity":    [],
                "swings":       {"highs": [], "lows": []},
            }

        highs  = np.array([c["high"]  for c in candles])
        lows   = np.array([c["low"]   for c in candles])
        closes = np.array([c["close"] for c in candles])
        opens  = np.array([c["open"]  for c in candles])
        times  = np.array([c["time"]  for c in candles])

        # Step 1: Find swing highs and lows
        swing_highs, swing_lows = self._find_swings(highs, lows)

        # Step 2: Detect market structure
        structure = self._detect_structure(
            highs, lows, closes, times, swing_highs, swing_lows
        )

        # Step 3: Detect order blocks
        order_blocks = self._detect_order_blocks(
            opens, highs, lows, closes, times, structure
        )

        # Step 4: Detect fair value gaps
        fvgs = self._detect_fvgs(highs, lows, closes, times)

        # Step 5: Detect liquidity levels
        liquidity = self._detect_liquidity(
            highs, lows, closes, times, swing_highs, swing_lows
        )

        self.result = {
            "order_blocks": order_blocks,
            "fvgs":         fvgs,
            "structure":    structure,
            "liquidity":    liquidity,
            "swings": {
                "highs": [(i, float(highs[i])) for i in swing_highs],
                "lows":  [(i, float(lows[i]))  for i in swing_lows],
            },
        }
        return self.result

    # ── Swing detection ───────────────────────────────────────────────────────

    def _find_swings(self, highs: np.ndarray, lows: np.ndarray):
        """
        Find swing highs and lows using lookback period.
        A swing high is a candle where high > all highs in lookback window.
        """
        n   = len(highs)
        lb  = self.swing_lookback
        swing_highs = []
        swing_lows  = []

        for i in range(lb, n - lb):
            window_h = highs[i - lb:i + lb + 1]
            window_l = lows[i  - lb:i + lb + 1]

            if highs[i] == np.max(window_h):
                swing_highs.append(i)
            if lows[i] == np.min(window_l):
                swing_lows.append(i)

        return swing_highs, swing_lows

    # ── Market structure ──────────────────────────────────────────────────────

    def _detect_structure(self, highs, lows, closes, times,
                          swing_highs, swing_lows) -> List[Dict]:
        """
        Detect Break of Structure (BOS) and Change of Character (CHoCH).

        BOS: continuation — price breaks in direction of trend
        CHoCH: reversal signal — price breaks against prevailing structure
        """
        events = []
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return events

        # Track trend: series of HH/HL = bullish, LH/LL = bearish
        trend = self._determine_trend(highs, lows, swing_highs, swing_lows)

        # Check for BOS/CHoCH at each new swing
        for i in range(1, len(swing_highs)):
            prev_idx = swing_highs[i - 1]
            curr_idx = swing_highs[i]

            if curr_idx >= len(highs):
                continue

            # Higher High → BOS bullish (if in uptrend) or CHoCH (if downtrend)
            if highs[curr_idx] > highs[prev_idx]:
                event_type = "BOS" if trend == "BULLISH" else "CHOCH"
                events.append({
                    "type":      event_type,
                    "direction": "BULLISH",
                    "price":     float(highs[curr_idx]),
                    "index":     int(curr_idx),
                    "time":      int(times[curr_idx]),
                    "broken_level": float(highs[prev_idx]),
                })
                if event_type == "CHOCH":
                    trend = "BULLISH"

        for i in range(1, len(swing_lows)):
            prev_idx = swing_lows[i - 1]
            curr_idx = swing_lows[i]

            if curr_idx >= len(lows):
                continue

            # Lower Low → BOS bearish or CHoCH
            if lows[curr_idx] < lows[prev_idx]:
                event_type = "BOS" if trend == "BEARISH" else "CHOCH"
                events.append({
                    "type":      event_type,
                    "direction": "BEARISH",
                    "price":     float(lows[curr_idx]),
                    "index":     int(curr_idx),
                    "time":      int(times[curr_idx]),
                    "broken_level": float(lows[prev_idx]),
                })
                if event_type == "CHOCH":
                    trend = "BEARISH"

        # Sort by time
        events.sort(key=lambda x: x["time"])
        return events

    def _determine_trend(self, highs, lows, swing_highs, swing_lows) -> str:
        """Determine prevailing trend from last 3 swings."""
        if len(swing_highs) >= 2:
            if highs[swing_highs[-1]] > highs[swing_highs[-2]]:
                return "BULLISH"
        if len(swing_lows) >= 2:
            if lows[swing_lows[-1]] < lows[swing_lows[-2]]:
                return "BEARISH"
        return "NEUTRAL"

    # ── Order Blocks ──────────────────────────────────────────────────────────

    def _detect_order_blocks(self, opens, highs, lows, closes,
                              times, structure) -> List[Dict]:
        """
        Detect Order Blocks.

        Bullish OB: Last bearish candle before a significant bullish move
                    (impulse that creates BOS/CHoCH upward)
        Bearish OB: Last bullish candle before a significant bearish move

        Strength scored 1-3 based on: displacement size, volume proxy,
        whether it created structure break.
        """
        obs = []
        n   = len(closes)

        # Get structure break indices for reference
        bos_indices = {e["index"] for e in structure if e["type"] in ("BOS", "CHOCH")}

        for i in range(2, n - 1):
            # Look for impulse moves (3+ candle displacement)
            if i + 3 >= n:
                break

            # Bullish OB: bearish candle followed by strong bullish move
            if closes[i] < opens[i]:  # bearish candle
                # Check if next 3 candles are strongly bullish
                future_move = closes[min(i+3, n-1)] - closes[i]
                candle_range = highs[i] - lows[i]
                if candle_range == 0:
                    continue

                displacement = future_move / closes[i]
                if displacement > 0.003:  # 0.3% minimum displacement
                    strength = self._score_ob_strength(
                        displacement, candle_range,
                        closes[i], i, bos_indices
                    )
                    obs.append({
                        "type":      "BULLISH_OB",
                        "top":       float(opens[i]),   # OB zone top = open of bearish candle
                        "bottom":    float(closes[i]),  # OB zone bottom = close
                        "high":      float(highs[i]),
                        "low":       float(lows[i]),
                        "index":     int(i),
                        "time":      int(times[i]),
                        "strength":  strength,
                        "mitigated": False,
                        "price_at_creation": float(closes[i]),
                    })

            # Bearish OB: bullish candle followed by strong bearish move
            elif closes[i] > opens[i]:  # bullish candle
                future_move = closes[i] - closes[min(i+3, n-1)]
                candle_range = highs[i] - lows[i]
                if candle_range == 0:
                    continue

                displacement = future_move / closes[i]
                if displacement > 0.003:
                    strength = self._score_ob_strength(
                        displacement, candle_range,
                        closes[i], i, bos_indices
                    )
                    obs.append({
                        "type":      "BEARISH_OB",
                        "top":       float(closes[i]),  # OB zone top = close of bullish candle
                        "bottom":    float(opens[i]),   # OB zone bottom = open
                        "high":      float(highs[i]),
                        "low":       float(lows[i]),
                        "index":     int(i),
                        "time":      int(times[i]),
                        "strength":  strength,
                        "mitigated": False,
                        "price_at_creation": float(closes[i]),
                    })

        # Check mitigation (price has returned to OB zone)
        current_price = float(closes[-1])
        for ob in obs:
            if ob["type"] == "BULLISH_OB":
                if current_price < ob["bottom"]:
                    ob["mitigated"] = True
            else:
                if current_price > ob["top"]:
                    ob["mitigated"] = True

        # Return last 10 unmitigated OBs
        active = [ob for ob in obs if not ob["mitigated"]]
        return active[-10:]

    def _score_ob_strength(self, displacement, candle_range,
                           price, index, bos_indices) -> int:
        """Score OB strength 1-3."""
        score = 1
        if displacement > 0.008:    # Strong displacement > 0.8%
            score += 1
        if index in bos_indices:    # Created a structure break
            score += 1
        return min(score, 3)

    # ── Fair Value Gaps ───────────────────────────────────────────────────────

    def _detect_fvgs(self, highs, lows, closes, times) -> List[Dict]:
        """
        Detect Fair Value Gaps (FVGs) / Imbalances.

        A bullish FVG exists when:
          candle[i-1].high < candle[i+1].low
          (gap between two candles that price hasn't filled)

        A bearish FVG exists when:
          candle[i-1].low > candle[i+1].high
        """
        fvgs = []
        n    = len(closes)

        for i in range(1, n - 1):
            # Bullish FVG: gap up — low of next candle > high of previous candle
            if lows[i + 1] > highs[i - 1]:
                gap_size = lows[i + 1] - highs[i - 1]
                gap_pct  = gap_size / closes[i]
                if gap_pct > 0.001:  # Minimum 0.1% gap
                    fvgs.append({
                        "type":      "BULLISH_FVG",
                        "top":       float(lows[i + 1]),
                        "bottom":    float(highs[i - 1]),
                        "mid":       float((lows[i + 1] + highs[i - 1]) / 2),
                        "index":     int(i),
                        "time":      int(times[i]),
                        "gap_pct":   round(gap_pct * 100, 3),
                        "filled":    False,
                        "fill_pct":  0.0,
                    })

            # Bearish FVG: gap down — high of next candle < low of previous candle
            elif highs[i + 1] < lows[i - 1]:
                gap_size = lows[i - 1] - highs[i + 1]
                gap_pct  = gap_size / closes[i]
                if gap_pct > 0.001:
                    fvgs.append({
                        "type":      "BEARISH_FVG",
                        "top":       float(lows[i - 1]),
                        "bottom":    float(highs[i + 1]),
                        "mid":       float((lows[i - 1] + highs[i + 1]) / 2),
                        "index":     int(i),
                        "time":      int(times[i]),
                        "gap_pct":   round(gap_pct * 100, 3),
                        "filled":    False,
                        "fill_pct":  0.0,
                    })

        # Check fill status against current price action
        current_high  = float(highs[-1])
        current_low   = float(lows[-1])

        for fvg in fvgs:
            if fvg["type"] == "BULLISH_FVG":
                if current_low <= fvg["top"] and current_high >= fvg["bottom"]:
                    penetration = (current_low - fvg["bottom"]) / (fvg["top"] - fvg["bottom"] + 1e-10)
                    fvg["fill_pct"] = max(0, min(100, (1 - penetration) * 100))
                    if current_low <= fvg["bottom"]:
                        fvg["filled"] = True
            else:
                if current_high >= fvg["bottom"] and current_low <= fvg["top"]:
                    penetration = (fvg["top"] - current_high) / (fvg["top"] - fvg["bottom"] + 1e-10)
                    fvg["fill_pct"] = max(0, min(100, (1 - penetration) * 100))
                    if current_high >= fvg["top"]:
                        fvg["filled"] = True

        # Return last 8 unfilled FVGs
        active = [f for f in fvgs if not f["filled"]]
        return active[-8:]

    # ── Liquidity ─────────────────────────────────────────────────────────────

    def _detect_liquidity(self, highs, lows, closes, times,
                           swing_highs, swing_lows) -> List[Dict]:
        """
        Detect liquidity levels:
          - Equal highs (buy-side liquidity)
          - Equal lows (sell-side liquidity)
          - Recent swing highs/lows (liquidity pools)
          - Stop hunt events (wick beyond swing then reversal)
        """
        liquidity = []
        n         = len(closes)
        tolerance = 0.001  # 0.1% price tolerance for "equal" levels

        # Equal highs (buy-side liquidity above)
        for i in range(len(swing_highs)):
            for j in range(i + 1, len(swing_highs)):
                hi = swing_highs[i]
                hj = swing_highs[j]
                if hi >= n or hj >= n:
                    continue
                diff = abs(highs[hi] - highs[hj]) / highs[hi]
                if diff < tolerance:
                    liquidity.append({
                        "type":    "EQUAL_HIGHS",
                        "price":   float((highs[hi] + highs[hj]) / 2),
                        "index_1": int(hi),
                        "index_2": int(hj),
                        "time":    int(times[hj]),
                        "swept":   float(closes[-1]) > float(highs[hj]),
                        "strength": 2,
                    })

        # Equal lows (sell-side liquidity below)
        for i in range(len(swing_lows)):
            for j in range(i + 1, len(swing_lows)):
                li = swing_lows[i]
                lj = swing_lows[j]
                if li >= n or lj >= n:
                    continue
                diff = abs(lows[li] - lows[lj]) / lows[li]
                if diff < tolerance:
                    liquidity.append({
                        "type":    "EQUAL_LOWS",
                        "price":   float((lows[li] + lows[lj]) / 2),
                        "index_1": int(li),
                        "index_2": int(lj),
                        "time":    int(times[lj]),
                        "swept":   float(closes[-1]) < float(lows[lj]),
                        "strength": 2,
                    })

        # Stop hunt detection (wick beyond swing then close back inside range)
        for i in range(2, n - 1):
            prev_swing_high = max(highs[max(0,i-10):i])
            prev_swing_low  = min(lows[max(0,i-10):i])

            # Bearish stop hunt: wick above then close below
            if (highs[i] > prev_swing_high and
                    closes[i] < prev_swing_high and
                    (highs[i] - closes[i]) > (closes[i] - lows[i]) * 1.5):
                liquidity.append({
                    "type":    "STOP_HUNT_BEARISH",
                    "price":   float(highs[i]),
                    "swept_level": float(prev_swing_high),
                    "index":   int(i),
                    "time":    int(times[i]),
                    "swept":   True,
                    "strength": 3,
                })

            # Bullish stop hunt: wick below then close above
            if (lows[i] < prev_swing_low and
                    closes[i] > prev_swing_low and
                    (closes[i] - lows[i]) > (highs[i] - closes[i]) * 1.5):
                liquidity.append({
                    "type":    "STOP_HUNT_BULLISH",
                    "price":   float(lows[i]),
                    "swept_level": float(prev_swing_low),
                    "index":   int(i),
                    "time":    int(times[i]),
                    "swept":   True,
                    "strength": 3,
                })

        return liquidity[-15:]

    # ── Confluence scoring ────────────────────────────────────────────────────

    def get_confluence_score(self, current_price: float) -> Dict:
        """
        Calculate SMC confluence score at current price.
        Returns dict with bullish_score, bearish_score, nearest_ob, nearest_fvg.
        """
        if not self.result:
            return {"bullish": 0, "bearish": 0}

        bullish = 0
        bearish = 0

        # Order block proximity
        for ob in self.result.get("order_blocks", []):
            dist_pct = abs(current_price - ob["mid"] if "mid" in ob
                          else (ob["top"] + ob["bottom"]) / 2) / current_price * 100
            if dist_pct < 1.0:  # Within 1% of OB
                if ob["type"] == "BULLISH_OB":
                    bullish += ob["strength"] * 10
                else:
                    bearish += ob["strength"] * 10

        # FVG proximity
        for fvg in self.result.get("fvgs", []):
            dist_pct = abs(current_price - fvg["mid"]) / current_price * 100
            if dist_pct < 0.5:
                if fvg["type"] == "BULLISH_FVG":
                    bullish += 15
                else:
                    bearish += 15

        # Recent structure
        recent_structure = self.result.get("structure", [])[-3:]
        for event in recent_structure:
            if event["direction"] == "BULLISH":
                bullish += 10 if event["type"] == "BOS" else 20
            else:
                bearish += 10 if event["type"] == "BOS" else 20

        # Recent stop hunts (reversal signal)
        recent_liq = [l for l in self.result.get("liquidity", [])
                      if l["type"].startswith("STOP_HUNT") and l["swept"]][-2:]
        for hunt in recent_liq:
            if hunt["type"] == "STOP_HUNT_BULLISH":
                bullish += 25
            else:
                bearish += 25

        return {
            "bullish": min(100, bullish),
            "bearish": min(100, bearish),
            "net":     min(100, max(-100, bullish - bearish)),
        }

    def get_nearest_ob(self, current_price: float) -> Optional[Dict]:
        """Return the nearest active order block to current price."""
        obs = self.result.get("order_blocks", [])
        if not obs:
            return None
        def ob_dist(ob):
            mid = (ob["top"] + ob["bottom"]) / 2
            return abs(current_price - mid)
        return min(obs, key=ob_dist)

    def get_nearest_fvg(self, current_price: float) -> Optional[Dict]:
        """Return the nearest unfilled FVG to current price."""
        fvgs = self.result.get("fvgs", [])
        if not fvgs:
            return None
        return min(fvgs, key=lambda f: abs(current_price - f["mid"]))

    def get_feature_vector(self, current_price: float) -> Dict[str, float]:
        """
        Extract SMC features as a flat dict for ML feature engineering.
        All values normalised to 0-1 or -1 to 1 range.
        """
        features = {
            "smc_bullish_score":     0.0,
            "smc_bearish_score":     0.0,
            "smc_net_score":         0.0,
            "nearest_ob_distance":   1.0,
            "nearest_ob_strength":   0.0,
            "nearest_ob_is_bullish": 0.0,
            "nearest_fvg_distance":  1.0,
            "nearest_fvg_is_bullish": 0.0,
            "recent_bos_bullish":    0.0,
            "recent_bos_bearish":    0.0,
            "recent_choch":          0.0,
            "stop_hunt_recent":      0.0,
            "equal_highs_nearby":    0.0,
            "equal_lows_nearby":     0.0,
        }

        if not self.result or current_price <= 0:
            return features

        score = self.get_confluence_score(current_price)
        features["smc_bullish_score"] = score["bullish"] / 100
        features["smc_bearish_score"] = score["bearish"] / 100
        features["smc_net_score"]     = score["net"]     / 100

        ob = self.get_nearest_ob(current_price)
        if ob:
            mid  = (ob["top"] + ob["bottom"]) / 2
            dist = abs(current_price - mid) / current_price
            features["nearest_ob_distance"]   = min(1.0, dist * 10)
            features["nearest_ob_strength"]   = ob["strength"] / 3
            features["nearest_ob_is_bullish"] = 1.0 if ob["type"] == "BULLISH_OB" else 0.0

        fvg = self.get_nearest_fvg(current_price)
        if fvg:
            dist = abs(current_price - fvg["mid"]) / current_price
            features["nearest_fvg_distance"]   = min(1.0, dist * 10)
            features["nearest_fvg_is_bullish"] = 1.0 if fvg["type"] == "BULLISH_FVG" else 0.0

        recent = self.result.get("structure", [])[-5:]
        for e in recent:
            if e["direction"] == "BULLISH":
                if e["type"] == "BOS":
                    features["recent_bos_bullish"] = 1.0
                else:
                    features["recent_choch"] = 1.0
            else:
                if e["type"] == "BOS":
                    features["recent_bos_bearish"] = 1.0
                else:
                    features["recent_choch"] = -1.0

        hunts = [l for l in self.result.get("liquidity", [])
                 if "STOP_HUNT" in l["type"]][-2:]
        if hunts:
            last = hunts[-1]
            features["stop_hunt_recent"] = (
                1.0 if last["type"] == "STOP_HUNT_BULLISH" else -1.0
            )

        liq = self.result.get("liquidity", [])
        for l in liq:
            if l["type"] == "EQUAL_HIGHS":
                dist = abs(current_price - l["price"]) / current_price
                if dist < 0.005:
                    features["equal_highs_nearby"] = 1.0
            elif l["type"] == "EQUAL_LOWS":
                dist = abs(current_price - l["price"]) / current_price
                if dist < 0.005:
                    features["equal_lows_nearby"] = 1.0

        return features
