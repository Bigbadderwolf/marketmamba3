# data/binance_executor.py
"""
Binance Trade Executor for Market Mamba.

Handles authenticated requests for:
  - Spot: market/limit/stop-limit orders, cancel, balances
  - Futures/Perpetuals: long/short, leverage, margin mode,
    position info, funding, liquidation price

API keys are loaded from encrypted storage — never hardcoded.
All order methods mirror Binance's own workflow exactly.
"""

import time
import hmac
import hashlib
import logging
import requests
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

from config.constants import BINANCE_REST_URL, BINANCE_FUTURES_URL

log = logging.getLogger(__name__)


# ── Request signing ───────────────────────────────────────────────────────────

def _sign(params: dict, secret: str) -> str:
    """Generate HMAC-SHA256 signature for Binance authenticated requests."""
    query = urlencode(params)
    return hmac.new(
        secret.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def _timestamp() -> int:
    return int(time.time() * 1000)


# ── Base authenticated client ─────────────────────────────────────────────────

class _BinanceClient:
    """
    Base authenticated HTTP client.
    Subclassed by SpotExecutor and FuturesExecutor.
    """

    def __init__(self, api_key: str, secret: str, base_url: str):
        self.api_key  = api_key
        self.secret   = secret
        self.base_url = base_url
        self._session = requests.Session()
        self._session.headers.update({
            "X-MBX-APIKEY": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent":   "MarketMamba/2.0",
        })
        self._time_offset = 0

    def _sync_time(self):
        """Sync local clock with Binance server to avoid timestamp errors."""
        try:
            resp = self._session.get(f"{self.base_url}/api/v3/time", timeout=5)
            server_ms = resp.json()["serverTime"]
            self._time_offset = server_ms - int(time.time() * 1000)
        except Exception:
            self._time_offset = 0

    def _signed_get(self, path: str, params: dict = None) -> dict:
        params = params or {}
        params["timestamp"]  = _timestamp() + self._time_offset
        params["recvWindow"] = 5000
        params["signature"]  = _sign(params, self.secret)

        resp = self._session.get(f"{self.base_url}{path}", params=params, timeout=10)
        self._handle_error(resp)
        return resp.json()

    def _signed_post(self, path: str, params: dict = None) -> dict:
        params = params or {}
        params["timestamp"]  = _timestamp() + self._time_offset
        params["recvWindow"] = 5000
        params["signature"]  = _sign(params, self.secret)

        resp = self._session.post(
            f"{self.base_url}{path}",
            data=urlencode(params),
            timeout=10
        )
        self._handle_error(resp)
        return resp.json()

    def _signed_delete(self, path: str, params: dict = None) -> dict:
        params = params or {}
        params["timestamp"]  = _timestamp() + self._time_offset
        params["recvWindow"] = 5000
        params["signature"]  = _sign(params, self.secret)

        resp = self._session.delete(
            f"{self.base_url}{path}",
            params=params,
            timeout=10
        )
        self._handle_error(resp)
        return resp.json()

    def _handle_error(self, resp: requests.Response):
        if resp.status_code == 200:
            return
        try:
            data = resp.json()
            code = data.get("code", resp.status_code)
            msg  = data.get("msg", resp.text)
            raise BinanceAPIError(code, msg)
        except ValueError:
            raise BinanceAPIError(resp.status_code, resp.text)


class BinanceAPIError(Exception):
    def __init__(self, code: int, msg: str):
        self.code = code
        self.msg  = msg
        super().__init__(f"Binance Error {code}: {msg}")


# ── Order result normaliser ───────────────────────────────────────────────────

def _parse_order(raw: dict) -> dict:
    """Normalise a Binance order response into a consistent dict."""
    return {
        "order_id":    str(raw.get("orderId", "")),
        "symbol":      raw.get("symbol", ""),
        "side":        raw.get("side", ""),
        "type":        raw.get("type", ""),
        "status":      raw.get("status", ""),
        "price":       float(raw.get("price", 0) or 0),
        "avg_price":   float(raw.get("avgPrice", 0) or raw.get("cummulativeQuoteQty", 0) or 0),
        "qty":         float(raw.get("origQty", 0) or 0),
        "filled_qty":  float(raw.get("executedQty", 0) or 0),
        "time_in_force": raw.get("timeInForce", "GTC"),
        "created_at":  int(raw.get("transactTime", raw.get("time", 0))) // 1000,
        "raw":         raw,
    }


# ── Spot Executor ─────────────────────────────────────────────────────────────

class SpotExecutor(_BinanceClient):
    """
    Handles all Spot trading operations.
    Mirrors Binance Spot trading workflow exactly.
    """

    def __init__(self, api_key: str, secret: str):
        super().__init__(api_key, secret, BINANCE_REST_URL)
        self._sync_time()

    # ── Account ───────────────────────────────────────────────────────────────

    def get_account(self) -> dict:
        """Get account info including balances."""
        return self._signed_get("/api/v3/account")

    def get_balances(self) -> Dict[str, dict]:
        """
        Get all non-zero balances.
        Returns dict: {"BTC": {"free": 0.5, "locked": 0.1}, ...}
        """
        account = self.get_account()
        balances = {}
        for b in account.get("balances", []):
            free   = float(b["free"])
            locked = float(b["locked"])
            if free > 0 or locked > 0:
                balances[b["asset"]] = {
                    "free":   free,
                    "locked": locked,
                    "total":  free + locked,
                }
        return balances

    def get_balance(self, asset: str = "USDT") -> float:
        """Get free balance for a specific asset."""
        bals = self.get_balances()
        return bals.get(asset.upper(), {}).get("free", 0.0)

    # ── Orders ────────────────────────────────────────────────────────────────

    def market_order(
        self,
        symbol:   str,
        side:     str,   # "BUY" or "SELL"
        quantity: float,
    ) -> dict:
        """
        Place a market order.
        side: "BUY" to go long / enter, "SELL" to exit.
        """
        params = {
            "symbol":   symbol.upper(),
            "side":     side.upper(),
            "type":     "MARKET",
            "quantity": self._fmt_qty(quantity, symbol),
        }
        log.info("SPOT MARKET %s %s qty=%s", side, symbol, quantity)
        raw = self._signed_post("/api/v3/order", params)
        return _parse_order(raw)

    def limit_order(
        self,
        symbol:    str,
        side:      str,
        quantity:  float,
        price:     float,
        time_in_force: str = "GTC",
    ) -> dict:
        """
        Place a limit order.
        time_in_force: GTC (default), IOC, FOK
        """
        params = {
            "symbol":      symbol.upper(),
            "side":        side.upper(),
            "type":        "LIMIT",
            "quantity":    self._fmt_qty(quantity, symbol),
            "price":       self._fmt_price(price, symbol),
            "timeInForce": time_in_force,
        }
        log.info("SPOT LIMIT %s %s qty=%s price=%s", side, symbol, quantity, price)
        raw = self._signed_post("/api/v3/order", params)
        return _parse_order(raw)

    def stop_limit_order(
        self,
        symbol:    str,
        side:      str,
        quantity:  float,
        price:     float,
        stop_price: float,
        time_in_force: str = "GTC",
    ) -> dict:
        """
        Place a stop-limit order.
        Triggers at stop_price, executes as limit at price.
        """
        params = {
            "symbol":      symbol.upper(),
            "side":        side.upper(),
            "type":        "STOP_LOSS_LIMIT",
            "quantity":    self._fmt_qty(quantity, symbol),
            "price":       self._fmt_price(price, symbol),
            "stopPrice":   self._fmt_price(stop_price, symbol),
            "timeInForce": time_in_force,
        }
        raw = self._signed_post("/api/v3/order", params)
        return _parse_order(raw)

    def oco_order(
        self,
        symbol:        str,
        side:          str,
        quantity:      float,
        price:         float,    # limit take profit price
        stop_price:    float,    # stop trigger
        stop_limit_price: float, # stop limit price
    ) -> dict:
        """
        Place an OCO (One-Cancels-the-Other) order.
        Used to set both take profit and stop loss simultaneously.
        """
        params = {
            "symbol":         symbol.upper(),
            "side":           side.upper(),
            "quantity":       self._fmt_qty(quantity, symbol),
            "price":          self._fmt_price(price, symbol),
            "stopPrice":      self._fmt_price(stop_price, symbol),
            "stopLimitPrice": self._fmt_price(stop_limit_price, symbol),
            "stopLimitTimeInForce": "GTC",
        }
        return self._signed_post("/api/v3/order/oco", params)

    def cancel_order(self, symbol: str, order_id: str) -> dict:
        """Cancel an open order."""
        params = {
            "symbol":  symbol.upper(),
            "orderId": int(order_id),
        }
        return self._signed_delete("/api/v3/order", params)

    def cancel_all_orders(self, symbol: str) -> list:
        """Cancel all open orders for a symbol."""
        params = {"symbol": symbol.upper()}
        return self._signed_delete("/api/v3/openOrders", params)

    def get_order(self, symbol: str, order_id: str) -> dict:
        """Get status of a specific order."""
        raw = self._signed_get("/api/v3/order", {
            "symbol":  symbol.upper(),
            "orderId": int(order_id),
        })
        return _parse_order(raw)

    def get_open_orders(self, symbol: str = None) -> List[dict]:
        """Get all open orders, optionally filtered by symbol."""
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        raw_list = self._signed_get("/api/v3/openOrders", params)
        return [_parse_order(r) for r in raw_list]

    def get_order_history(self, symbol: str, limit: int = 50) -> List[dict]:
        """Get recent order history for a symbol."""
        raw_list = self._signed_get("/api/v3/allOrders", {
            "symbol": symbol.upper(),
            "limit":  limit,
        })
        return [_parse_order(r) for r in raw_list]

    # ── Formatting helpers ────────────────────────────────────────────────────

    def _fmt_qty(self, qty: float, symbol: str) -> str:
        """Format quantity to correct decimal places for symbol."""
        from data.binance_rest import get_symbol_filters
        filters = get_symbol_filters(symbol)
        step = filters.get("step_size", 0.00001)
        decimals = len(str(step).rstrip("0").split(".")[-1]) if "." in str(step) else 0
        return f"{qty:.{decimals}f}"

    def _fmt_price(self, price: float, symbol: str) -> str:
        """Format price to correct decimal places for symbol."""
        from data.binance_rest import get_symbol_filters
        filters = get_symbol_filters(symbol)
        tick = filters.get("tick_size", 0.01)
        decimals = len(str(tick).rstrip("0").split(".")[-1]) if "." in str(tick) else 2
        return f"{price:.{decimals}f}"


# ── Futures Executor ──────────────────────────────────────────────────────────

class FuturesExecutor(_BinanceClient):
    """
    Handles all Futures/Perpetuals trading operations.
    Supports: long/short, leverage (1-125x), cross/isolated margin,
    TP/SL orders, position info, funding rate.
    """

    def __init__(self, api_key: str, secret: str):
        super().__init__(api_key, secret, BINANCE_FUTURES_URL)
        self._fapi_base = BINANCE_FUTURES_URL
        self._sync_time()

    # Override to use fapi endpoints
    def _signed_get(self, path: str, params: dict = None) -> dict:
        params = params or {}
        params["timestamp"]  = _timestamp() + self._time_offset
        params["recvWindow"] = 5000
        params["signature"]  = _sign(params, self.secret)
        resp = self._session.get(f"{self._fapi_base}{path}", params=params, timeout=10)
        self._handle_error(resp)
        return resp.json()

    def _signed_post(self, path: str, params: dict = None) -> dict:
        params = params or {}
        params["timestamp"]  = _timestamp() + self._time_offset
        params["recvWindow"] = 5000
        params["signature"]  = _sign(params, self.secret)
        resp = self._session.post(
            f"{self._fapi_base}{path}",
            data=urlencode(params),
            timeout=10
        )
        self._handle_error(resp)
        return resp.json()

    def _signed_delete(self, path: str, params: dict = None) -> dict:
        params = params or {}
        params["timestamp"]  = _timestamp() + self._time_offset
        params["recvWindow"] = 5000
        params["signature"]  = _sign(params, self.secret)
        resp = self._session.delete(
            f"{self._fapi_base}{path}",
            params=params,
            timeout=10
        )
        self._handle_error(resp)
        return resp.json()

    # ── Account ───────────────────────────────────────────────────────────────

    def get_account(self) -> dict:
        """Get futures account info."""
        return self._signed_get("/fapi/v2/account")

    def get_balance(self, asset: str = "USDT") -> float:
        """Get available futures wallet balance."""
        try:
            balances = self._signed_get("/fapi/v2/balance")
            for b in balances:
                if b.get("asset") == asset.upper():
                    return float(b.get("availableBalance", 0))
        except Exception as e:
            log.error("get_futures_balance failed: %s", e)
        return 0.0

    def get_positions(self, symbol: str = None) -> List[dict]:
        """
        Get all open positions (or filtered by symbol).
        Returns normalised position dicts.
        """
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        raw = self._signed_get("/fapi/v2/positionRisk", params)
        positions = []
        for p in raw:
            qty = float(p.get("positionAmt", 0))
            if qty == 0 and symbol is None:
                continue
            positions.append({
                "symbol":         p["symbol"],
                "side":           "LONG" if qty > 0 else "SHORT" if qty < 0 else "NONE",
                "qty":            abs(qty),
                "entry_price":    float(p.get("entryPrice", 0)),
                "mark_price":     float(p.get("markPrice", 0)),
                "pnl":            float(p.get("unRealizedProfit", 0)),
                "leverage":       int(p.get("leverage", 1)),
                "margin_type":    p.get("marginType", "cross"),
                "liq_price":      float(p.get("liquidationPrice", 0)),
                "margin":         float(p.get("isolatedMargin", 0)),
                "raw":            p,
            })
        return positions

    # ── Leverage & margin ─────────────────────────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        """
        Set leverage for a symbol (1–125x).
        Must be called before placing orders.
        """
        leverage = max(1, min(125, int(leverage)))
        result = self._signed_post("/fapi/v1/leverage", {
            "symbol":   symbol.upper(),
            "leverage": leverage,
        })
        log.info("Set leverage %dx for %s", leverage, symbol)
        return result

    def set_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> dict:
        """
        Set margin mode: "CROSSED" (cross) or "ISOLATED".
        """
        margin_type = margin_type.upper()
        if margin_type not in ("CROSSED", "ISOLATED"):
            raise ValueError("margin_type must be CROSSED or ISOLATED")
        try:
            result = self._signed_post("/fapi/v1/marginType", {
                "symbol":     symbol.upper(),
                "marginType": margin_type,
            })
            log.info("Set margin type %s for %s", margin_type, symbol)
            return result
        except BinanceAPIError as e:
            if e.code == -4046:   # "No need to change margin type" — already set
                return {"msg": "Already set"}
            raise

    def get_max_leverage(self, symbol: str) -> int:
        """Get maximum allowed leverage for a symbol."""
        try:
            brackets = self._signed_get("/fapi/v1/leverageBracket", {
                "symbol": symbol.upper()
            })
            if brackets and isinstance(brackets, list):
                brackets_data = brackets[0].get("brackets", [])
                if brackets_data:
                    return int(brackets_data[0].get("initialLeverage", 125))
        except Exception:
            pass
        return 125

    # ── Orders ────────────────────────────────────────────────────────────────

    def market_order(
        self,
        symbol:         str,
        side:           str,   # "BUY" (long) or "SELL" (short)
        quantity:       float,
        reduce_only:    bool = False,
        position_side:  str = "BOTH",  # "BOTH", "LONG", "SHORT"
    ) -> dict:
        """
        Place a futures market order.
        BUY = open long / close short
        SELL = open short / close long
        """
        params = {
            "symbol":       symbol.upper(),
            "side":         side.upper(),
            "type":         "MARKET",
            "quantity":     f"{quantity:.3f}",
            "positionSide": position_side,
        }
        if reduce_only:
            params["reduceOnly"] = "true"

        log.info("FUTURES MARKET %s %s qty=%s", side, symbol, quantity)
        raw = self._signed_post("/fapi/v1/order", params)
        return _parse_order(raw)

    def limit_order(
        self,
        symbol:         str,
        side:           str,
        quantity:       float,
        price:          float,
        time_in_force:  str = "GTC",
        reduce_only:    bool = False,
        position_side:  str = "BOTH",
    ) -> dict:
        """Place a futures limit order."""
        params = {
            "symbol":       symbol.upper(),
            "side":         side.upper(),
            "type":         "LIMIT",
            "quantity":     f"{quantity:.3f}",
            "price":        f"{price:.2f}",
            "timeInForce":  time_in_force,
            "positionSide": position_side,
        }
        if reduce_only:
            params["reduceOnly"] = "true"

        raw = self._signed_post("/fapi/v1/order", params)
        return _parse_order(raw)

    def stop_market_order(
        self,
        symbol:         str,
        side:           str,
        quantity:       float,
        stop_price:     float,
        reduce_only:    bool = True,
        position_side:  str = "BOTH",
    ) -> dict:
        """
        Place a stop-market order (for stop loss).
        Triggered at stop_price, executes at market.
        """
        params = {
            "symbol":       symbol.upper(),
            "side":         side.upper(),
            "type":         "STOP_MARKET",
            "quantity":     f"{quantity:.3f}",
            "stopPrice":    f"{stop_price:.2f}",
            "positionSide": position_side,
        }
        if reduce_only:
            params["reduceOnly"] = "true"

        raw = self._signed_post("/fapi/v1/order", params)
        return _parse_order(raw)

    def take_profit_market_order(
        self,
        symbol:         str,
        side:           str,
        quantity:       float,
        stop_price:     float,
        reduce_only:    bool = True,
        position_side:  str = "BOTH",
    ) -> dict:
        """
        Place a take-profit-market order.
        Triggered at stop_price, executes at market.
        """
        params = {
            "symbol":       symbol.upper(),
            "side":         side.upper(),
            "type":         "TAKE_PROFIT_MARKET",
            "quantity":     f"{quantity:.3f}",
            "stopPrice":    f"{stop_price:.2f}",
            "positionSide": position_side,
        }
        if reduce_only:
            params["reduceOnly"] = "true"

        raw = self._signed_post("/fapi/v1/order", params)
        return _parse_order(raw)

    def place_with_tp_sl(
        self,
        symbol:      str,
        side:        str,
        quantity:    float,
        order_type:  str = "MARKET",
        entry_price: float = None,
        take_profit: float = None,
        stop_loss:   float = None,
        leverage:    int = None,
        margin_type: str = "CROSSED",
    ) -> dict:
        """
        Complete trade entry: sets leverage, margin mode,
        places entry order, then attaches TP and SL orders.
        Returns dict with entry_order, tp_order, sl_order.
        """
        # Set leverage and margin type first
        if leverage:
            self.set_leverage(symbol, leverage)
        self.set_margin_type(symbol, margin_type)

        # Determine close side
        close_side = "SELL" if side.upper() == "BUY" else "BUY"

        # Entry order
        if order_type.upper() == "MARKET":
            entry = self.market_order(symbol, side, quantity)
        else:
            if not entry_price:
                raise ValueError("entry_price required for limit orders")
            entry = self.limit_order(symbol, side, quantity, entry_price)

        result = {"entry_order": entry, "tp_order": None, "sl_order": None}

        # Take profit
        if take_profit:
            try:
                result["tp_order"] = self.take_profit_market_order(
                    symbol, close_side, quantity, take_profit
                )
            except Exception as e:
                log.error("Failed to place TP order: %s", e)

        # Stop loss
        if stop_loss:
            try:
                result["sl_order"] = self.stop_market_order(
                    symbol, close_side, quantity, stop_loss
                )
            except Exception as e:
                log.error("Failed to place SL order: %s", e)

        return result

    def close_position(self, symbol: str, position: dict = None) -> dict:
        """
        Close an open position at market price.
        Fetches current position if not provided.
        """
        if not position:
            positions = self.get_positions(symbol)
            if not positions:
                raise RuntimeError(f"No open position for {symbol}")
            position = positions[0]

        qty       = position["qty"]
        pos_side  = position["side"]
        close_side = "SELL" if pos_side == "LONG" else "BUY"

        return self.market_order(
            symbol=symbol,
            side=close_side,
            quantity=qty,
            reduce_only=True,
        )

    def cancel_order(self, symbol: str, order_id: str) -> dict:
        return self._signed_delete("/fapi/v1/order", {
            "symbol":  symbol.upper(),
            "orderId": int(order_id),
        })

    def cancel_all_orders(self, symbol: str) -> dict:
        return self._signed_delete("/fapi/v1/allOpenOrders", {
            "symbol": symbol.upper()
        })

    def get_open_orders(self, symbol: str = None) -> List[dict]:
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        raw_list = self._signed_get("/fapi/v1/openOrders", params)
        return [_parse_order(r) for r in raw_list]

    def get_trade_history(self, symbol: str, limit: int = 50) -> List[dict]:
        """Get recent trade history for a symbol."""
        raw = self._signed_get("/fapi/v1/userTrades", {
            "symbol": symbol.upper(),
            "limit":  limit,
        })
        return raw


# ── Factory ───────────────────────────────────────────────────────────────────

def create_executor(
    user_id:      int,
    account_type: str = "spot",
) -> Optional[SpotExecutor | FuturesExecutor]:
    """
    Create an executor for a user by loading their encrypted API keys.
    Returns None if no keys are stored for this account type.
    """
    try:
        from auth.db import get_conn
        from auth.crypto_store import load_api_keys

        conn = get_conn()
        keys = load_api_keys(conn, user_id, account_type)
        conn.close()

        if not keys:
            log.warning("No %s API keys found for user %s", account_type, user_id)
            return None

        api_key, secret = keys

        if account_type == "futures":
            return FuturesExecutor(api_key, secret)
        else:
            return SpotExecutor(api_key, secret)

    except Exception as e:
        log.error("create_executor failed: %s", e)
        return None


# ── Position size calculator ──────────────────────────────────────────────────

def calculate_position_size(
    balance:       float,
    risk_pct:      float,
    entry_price:   float,
    stop_loss:     float,
    leverage:      int = 1,
) -> Tuple[float, float]:
    """
    Calculate position size based on risk management.

    Args:
        balance:     Account balance in USDT
        risk_pct:    % of balance to risk (e.g. 1.0 for 1%)
        entry_price: Trade entry price
        stop_loss:   Stop loss price
        leverage:    Leverage multiplier (futures only)

    Returns:
        (quantity, margin_required)
        quantity: number of contracts/coins to buy
        margin:   USDT margin required
    """
    if entry_price <= 0 or stop_loss <= 0:
        return 0.0, 0.0

    risk_amount   = balance * (risk_pct / 100)
    price_diff    = abs(entry_price - stop_loss)
    risk_per_unit = price_diff

    if risk_per_unit <= 0:
        return 0.0, 0.0

    quantity       = risk_amount / risk_per_unit
    notional_value = quantity * entry_price
    margin_required = notional_value / leverage

    return round(quantity, 6), round(margin_required, 2)


def calculate_rr_ratio(
    entry:       float,
    stop_loss:   float,
    take_profit: float,
    side:        str = "BUY",
) -> float:
    """Calculate Risk:Reward ratio for a trade."""
    if side.upper() == "BUY":
        risk   = entry - stop_loss
        reward = take_profit - entry
    else:
        risk   = stop_loss - entry
        reward = entry - take_profit

    if risk <= 0:
        return 0.0

    return round(reward / risk, 2)
