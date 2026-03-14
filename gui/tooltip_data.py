# gui/tooltip_data.py
"""
Complete tooltip content for all indicators and SMC concepts.
Each entry contains:
  - name:        Full display name
  - description: What it measures / how it works
  - how_to_read: How to interpret the signal
  - buy_signal:  What constitutes a buy signal
  - sell_signal: What constitutes a sell signal
  - tip:         Pro trading tip
"""

INDICATOR_TOOLTIPS = {

    "EMA_9": {
        "name": "EMA 9 — Exponential Moving Average (9)",
        "description": (
            "A fast-reacting moving average that weights recent prices more heavily "
            "than older ones. The 9-period EMA responds quickly to price changes, "
            "making it ideal for short-term momentum detection on any timeframe."
        ),
        "how_to_read": (
            "When price is above EMA 9 → short-term bullish momentum.\n"
            "When price is below EMA 9 → short-term bearish momentum.\n"
            "EMA 9 crossing above EMA 21 → bullish crossover signal."
        ),
        "buy_signal":  "Price bounces off EMA 9 from above, or EMA 9 crosses above EMA 21.",
        "sell_signal": "Price rejects EMA 9 from below, or EMA 9 crosses below EMA 21.",
        "tip": "Best used in trending markets. In ranging markets EMA 9 generates false signals."
    },

    "EMA_21": {
        "name": "EMA 21 — Exponential Moving Average (21)",
        "description": (
            "A medium-term EMA widely used by professional traders. The 21 EMA acts as "
            "dynamic support in uptrends and dynamic resistance in downtrends. "
            "It is the most commonly watched EMA on crypto and forex charts."
        ),
        "how_to_read": (
            "Price consistently closing above EMA 21 → uptrend confirmed.\n"
            "Price consistently closing below EMA 21 → downtrend confirmed.\n"
            "Multiple touches of EMA 21 without breaking = strong trend."
        ),
        "buy_signal":  "Price pulls back to EMA 21 in an uptrend and holds — classic buy zone.",
        "sell_signal": "Price rallies to EMA 21 in a downtrend and rejects — classic short zone.",
        "tip": "Combine with EMA 200 for trend context. Only take EMA 21 bounces in the direction of EMA 200."
    },

    "EMA_50": {
        "name": "EMA 50 — Exponential Moving Average (50)",
        "description": (
            "The 50 EMA represents medium-to-long term trend direction. It is widely "
            "watched by institutional traders and often acts as a major inflection point "
            "where large buyers and sellers are active."
        ),
        "how_to_read": (
            "EMA 50 above EMA 200 → bullish market structure (golden zone).\n"
            "EMA 50 below EMA 200 → bearish market structure (death zone).\n"
            "Price reclaiming EMA 50 after extended sell-off = strong reversal signal."
        ),
        "buy_signal":  "Price reclaims EMA 50 with strong volume after a pullback.",
        "sell_signal": "Price fails to reclaim EMA 50 after multiple attempts — continuation short.",
        "tip": "The 50/200 EMA crossover (Golden Cross / Death Cross) is one of the most reliable macro signals."
    },

    "EMA_200": {
        "name": "EMA 200 — Exponential Moving Average (200)",
        "description": (
            "The most important moving average in trading. The 200 EMA defines the "
            "long-term trend on any timeframe and is used by hedge funds, banks, and "
            "institutional traders worldwide. Price above 200 EMA = bull market. "
            "Price below 200 EMA = bear market."
        ),
        "how_to_read": (
            "Price above EMA 200 → macro bullish — only take long setups.\n"
            "Price below EMA 200 → macro bearish — only take short setups.\n"
            "First touch of EMA 200 after extended trend = very high probability reversal."
        ),
        "buy_signal":  "Price touches EMA 200 from above in a bull market — highest probability buy zone.",
        "sell_signal": "Price rallies back to EMA 200 from below in a bear market — high probability short.",
        "tip": "Never fight the 200 EMA. If price is below it, reduce long exposure regardless of other signals."
    },

    "VWAP": {
        "name": "VWAP — Volume Weighted Average Price",
        "description": (
            "VWAP calculates the average price weighted by volume throughout the session. "
            "It is the single most important intraday indicator used by institutional traders "
            "and market makers. Large orders are benchmarked against VWAP — institutions "
            "buying below VWAP get a 'good fill', selling above VWAP gets a 'good fill'."
        ),
        "how_to_read": (
            "Price above VWAP → bullish intraday bias, institutions are buyers.\n"
            "Price below VWAP → bearish intraday bias, institutions are sellers.\n"
            "VWAP reclaim after dip = strong continuation signal.\n"
            "VWAP rejection = confirms bearish bias."
        ),
        "buy_signal":  "Price dips below VWAP then reclaims it with a bullish candle close.",
        "sell_signal": "Price rallies above VWAP then fails and closes back below it.",
        "tip": "Most effective on 1m–1h timeframes. Resets each session — most powerful at open."
    },

    "RSI": {
        "name": "RSI — Relative Strength Index (14)",
        "description": (
            "RSI measures the speed and magnitude of recent price changes on a 0–100 scale. "
            "It identifies overbought conditions (above 70) where price may be due for a "
            "pullback, and oversold conditions (below 30) where price may bounce. "
            "Developed by J. Welles Wilder — one of the most used indicators globally."
        ),
        "how_to_read": (
            "RSI > 70 → Overbought — potential sell/short zone.\n"
            "RSI < 30 → Oversold — potential buy/long zone.\n"
            "RSI 40–60 → Neutral range.\n"
            "Bullish divergence: price makes lower low but RSI makes higher low → reversal up.\n"
            "Bearish divergence: price makes higher high but RSI makes lower high → reversal down."
        ),
        "buy_signal":  "RSI drops below 30 (oversold) then crosses back above 30 with bullish candle.",
        "sell_signal": "RSI rises above 70 (overbought) then crosses back below 70 with bearish candle.",
        "tip": "RSI divergence is more reliable than overbought/oversold alone. Always check for divergence."
    },

    "STOCHRSI": {
        "name": "Stochastic RSI",
        "description": (
            "Stochastic RSI applies the Stochastic oscillator to RSI values rather than "
            "price, making it more sensitive than standard RSI. It oscillates between 0–100 "
            "with K line (fast) and D line (slow). Excellent for identifying precise entry "
            "and exit timing within a larger trend."
        ),
        "how_to_read": (
            "K and D both below 20 → oversold — potential reversal up.\n"
            "K and D both above 80 → overbought — potential reversal down.\n"
            "K crossing above D in oversold zone → buy trigger.\n"
            "K crossing below D in overbought zone → sell trigger."
        ),
        "buy_signal":  "K line crosses above D line while both are below 20 (oversold zone crossover).",
        "sell_signal": "K line crosses below D line while both are above 80 (overbought zone crossover).",
        "tip": "Only trade Stoch RSI signals in the direction of the higher timeframe trend."
    },

    "MACD": {
        "name": "MACD — Moving Average Convergence Divergence (12/26/9)",
        "description": (
            "MACD tracks the relationship between two EMAs (12 and 26 period). "
            "The MACD line minus the signal line creates the histogram — showing "
            "momentum acceleration and deceleration. One of the most versatile "
            "trend-following momentum indicators available."
        ),
        "how_to_read": (
            "MACD line above Signal line → bullish momentum.\n"
            "MACD line below Signal line → bearish momentum.\n"
            "Histogram growing → momentum accelerating in that direction.\n"
            "Histogram shrinking → momentum weakening — potential reversal ahead.\n"
            "MACD crossing zero line → major trend change signal."
        ),
        "buy_signal":  "MACD line crosses above Signal line below zero level (most powerful buy signal).",
        "sell_signal": "MACD line crosses below Signal line above zero level (most powerful sell signal).",
        "tip": "MACD crossovers above/below zero are stronger than crossovers in the middle. Wait for zero-line crosses for high-conviction trades."
    },

    "BB": {
        "name": "Bollinger Bands (20, 2σ)",
        "description": (
            "Bollinger Bands place two standard deviation bands above and below a 20-period "
            "SMA. When bands are narrow (squeeze), volatility is low — a breakout is "
            "imminent. When bands are wide, volatility is high. Price statistically stays "
            "within the bands 95% of the time, making touches of the bands high-probability "
            "mean reversion or breakout signals."
        ),
        "how_to_read": (
            "Price touching upper band → overbought in range, or strong uptrend continuation.\n"
            "Price touching lower band → oversold in range, or strong downtrend continuation.\n"
            "Band squeeze (narrow bands) → breakout coming — direction unknown.\n"
            "Price walking the upper band → strong uptrend, do not fade.\n"
            "Price walking the lower band → strong downtrend, do not buy."
        ),
        "buy_signal":  "Price touches lower band, middle band is flat (ranging) — mean reversion buy.",
        "sell_signal": "Price touches upper band, middle band is flat (ranging) — mean reversion sell.",
        "tip": "In strong trends, price can 'walk the band' for extended periods. Combine with RSI to distinguish trend from range."
    },

    "ATR": {
        "name": "ATR — Average True Range (14)",
        "description": (
            "ATR measures market volatility by calculating the average range of price "
            "movement per candle over 14 periods. It does not indicate direction — only "
            "how much price is moving. Essential for position sizing and stop loss placement. "
            "A 1.5–2x ATR stop loss is the professional standard."
        ),
        "how_to_read": (
            "High ATR → high volatility — widen stops, reduce position size.\n"
            "Low ATR → low volatility — tighter stops possible, breakout may be forming.\n"
            "ATR expanding after contraction → volatility returning, breakout underway.\n"
            "Stop loss placement: entry price ± (1.5 × ATR)."
        ),
        "buy_signal":  "ATR is not a directional signal. Use for stop placement: Long stop = entry - 1.5×ATR.",
        "sell_signal": "Short stop = entry + 1.5×ATR. Size position so 1.5×ATR loss = your max risk %.",
        "tip": "Never place stops tighter than 1×ATR — you will be stopped out by normal volatility."
    },

    "ICHIMOKU": {
        "name": "Ichimoku Cloud (9/26/52)",
        "description": (
            "Ichimoku is a complete trading system showing trend, momentum, support, "
            "resistance and signals all in one indicator. Developed in Japan in the 1960s. "
            "The cloud (Kumo) is the most important element — it shows future support/resistance. "
            "Widely used by professional traders, especially in Asian sessions."
        ),
        "how_to_read": (
            "Price above cloud → bullish — only take longs.\n"
            "Price below cloud → bearish — only take shorts.\n"
            "Price inside cloud → neutral/choppy — avoid trading.\n"
            "Tenkan (red) crossing above Kijun (blue) → TK cross buy signal.\n"
            "Tenkan crossing below Kijun → TK cross sell signal.\n"
            "Thick green cloud ahead → strong support. Thin cloud = weak support."
        ),
        "buy_signal":  "Price above cloud + Tenkan crosses above Kijun + chikou above price = triple confirmation buy.",
        "sell_signal": "Price below cloud + Tenkan crosses below Kijun + chikou below price = triple confirmation sell.",
        "tip": "The strongest Ichimoku signals occur when all 5 components align. Partial alignment = lower conviction."
    },

    "OBV": {
        "name": "OBV — On Balance Volume",
        "description": (
            "OBV tracks cumulative volume flow. When price closes up, volume is added. "
            "When price closes down, volume is subtracted. OBV reveals whether volume "
            "is flowing into or out of an asset — showing the conviction behind price moves. "
            "Smart money accumulation shows up in OBV before price moves."
        ),
        "how_to_read": (
            "OBV rising with price → healthy uptrend, volume confirms move.\n"
            "OBV falling with price → healthy downtrend, volume confirms move.\n"
            "OBV rising while price flat/falling → accumulation — bullish divergence.\n"
            "OBV falling while price flat/rising → distribution — bearish divergence."
        ),
        "buy_signal":  "OBV making new highs while price consolidates — smart money accumulating before breakout.",
        "sell_signal": "OBV making lower lows while price is still high — distribution before price drops.",
        "tip": "OBV divergence from price is one of the strongest leading indicators of reversals."
    },

    "CVD": {
        "name": "CVD — Cumulative Volume Delta",
        "description": (
            "CVD measures the net difference between buying and selling volume. "
            "Unlike OBV, CVD approximates actual aggressive buying vs selling pressure "
            "using candle structure. A rising CVD means buyers are more aggressive. "
            "Falling CVD means sellers are in control."
        ),
        "how_to_read": (
            "CVD rising → buyers are dominant — bullish pressure building.\n"
            "CVD falling → sellers are dominant — bearish pressure building.\n"
            "CVD diverging from price → smart money positioning against the trend.\n"
            "CVD flat while price rises → weak move — likely to reverse."
        ),
        "buy_signal":  "CVD turns up after sustained decline + price at support = buyers absorbing selling pressure.",
        "sell_signal": "CVD turns down after sustained rise + price at resistance = sellers absorbing buying pressure.",
        "tip": "CVD is most useful on 1m–15m timeframes for precision entry timing."
    },
}


SMC_TOOLTIPS = {

    "OB": {
        "name": "Order Blocks",
        "description": (
            "Order Blocks (OBs) are the last opposing candle before a significant impulsive "
            "move. They represent zones where institutional orders (banks, hedge funds) were "
            "placed. When price returns to these zones, institutions re-enter their positions, "
            "causing strong reversals. The most powerful entry zones in Smart Money trading."
        ),
        "how_to_read": (
            "Bullish OB (green zone): Last bearish candle before a strong bullish impulse.\n"
            "  → When price returns to this zone from above = buy zone.\n"
            "Bearish OB (red zone): Last bullish candle before a strong bearish impulse.\n"
            "  → When price returns to this zone from below = sell/short zone.\n"
            "Strength 1-3: Higher = more institutional interest in that zone.\n"
            "Mitigated OB: Zone has been tested — less reliable for future entries."
        ),
        "buy_signal":  "Price returns to a Bullish OB zone and shows bullish reaction (rejection wick, engulfing candle).",
        "sell_signal": "Price returns to a Bearish OB zone and shows bearish reaction.",
        "tip": "The strongest OBs are those that caused a BOS or CHoCH — they have institutional order flow behind them."
    },

    "FVG": {
        "name": "Fair Value Gaps (FVG) — Imbalances",
        "description": (
            "A Fair Value Gap occurs when price moves so aggressively that it leaves a gap "
            "between two candles that has not been traded through. These gaps represent price "
            "inefficiency — the market 'wants' to return to fill them. Also called imbalances "
            "or price inefficiencies. FVGs are magnets for price."
        ),
        "how_to_read": (
            "Bullish FVG (blue zone above price): Gap left during upward impulse.\n"
            "  → Price often returns to fill the FVG before continuing up.\n"
            "Bearish FVG (blue zone below price): Gap left during downward impulse.\n"
            "  → Price often returns to fill the FVG before continuing down.\n"
            "Fill % shows how much of the gap has been covered by price.\n"
            "Unfilled FVGs are active magnets — price will likely return."
        ),
        "buy_signal":  "Price drops into a Bullish FVG (equilibrium retest) and shows rejection — enter long.",
        "sell_signal": "Price rises into a Bearish FVG and shows rejection — enter short.",
        "tip": "Confluence of FVG + Order Block in the same zone = extremely high probability setup."
    },

    "BOS": {
        "name": "BOS / CHoCH — Market Structure",
        "description": (
            "Break of Structure (BOS) and Change of Character (CHoCH) define the market's "
            "directional bias.\n\n"
            "BOS: Price breaks a previous swing high/low in the SAME direction as the trend. "
            "Confirms trend continuation.\n\n"
            "CHoCH: Price breaks a swing in the OPPOSITE direction to the current trend. "
            "This is the first signal of a potential trend reversal — the most important "
            "signal in SMC trading."
        ),
        "how_to_read": (
            "Bullish BOS (green line): Higher high broken → uptrend continuing.\n"
            "Bearish BOS (red line): Lower low broken → downtrend continuing.\n"
            "Bullish CHoCH: First higher high after a downtrend → reversal signal up.\n"
            "Bearish CHoCH: First lower low after an uptrend → reversal signal down.\n"
            "The level at which BOS/CHoCH occurred becomes key support/resistance."
        ),
        "buy_signal":  "Bullish CHoCH confirmed — first higher high after downtrend. Enter long on retest of CHoCH level.",
        "sell_signal": "Bearish CHoCH confirmed — first lower low after uptrend. Enter short on retest of CHoCH level.",
        "tip": "Do not chase BOS/CHoCH breakouts. Wait for price to return and retest the broken level before entering."
    },

    "LIQ": {
        "name": "Liquidity — Stop Hunts & Equal Levels",
        "description": (
            "Liquidity levels mark where stop losses are clustered. Retail traders place "
            "stops just above swing highs (buy stops) and below swing lows (sell stops). "
            "Institutions hunt these levels to fill their large orders cheaply before "
            "reversing. Understanding liquidity tells you WHERE institutions will push price "
            "before making the real move."
        ),
        "how_to_read": (
            "Equal Highs (yellow line above): Buy-stop liquidity pool — price likely to spike "
            "above to grab stops before dropping.\n"
            "Equal Lows (yellow line below): Sell-stop liquidity pool — price likely to spike "
            "below to grab stops before rising.\n"
            "Stop Hunt Bearish: Wick above swing high, closed back below → bears took liquidity, "
            "now going down.\n"
            "Stop Hunt Bullish: Wick below swing low, closed back above → bulls took liquidity, "
            "now going up."
        ),
        "buy_signal":  "Bullish stop hunt: Price wicks below Equal Lows and immediately closes back above — strong buy.",
        "sell_signal": "Bearish stop hunt: Price wicks above Equal Highs and immediately closes back below — strong sell.",
        "tip": "Never place your stop at the obvious swing high/low — that is exactly where institutions hunt. Add 1×ATR buffer."
    },

    "SWING": {
        "name": "Swing Highs & Lows",
        "description": (
            "Swing points are locally significant highs and lows that define market structure. "
            "They are the building blocks of all SMC analysis — every OB, FVG, BOS and "
            "liquidity level is derived from swing points. Swing highs are resistance until "
            "broken; swing lows are support until broken."
        ),
        "how_to_read": (
            "Series of Higher Highs + Higher Lows → uptrend structure.\n"
            "Series of Lower Highs + Lower Lows → downtrend structure.\n"
            "Last swing high = key resistance level to watch.\n"
            "Last swing low = key support level to watch.\n"
            "Breaking a swing with strong volume = high probability of trend continuation."
        ),
        "buy_signal":  "Price makes Higher Low (does not break previous swing low) + breaks previous swing high = confirmed uptrend.",
        "sell_signal": "Price makes Lower High (does not break previous swing high) + breaks previous swing low = confirmed downtrend.",
        "tip": "Always identify the most recent swing high and low before placing any trade. They define your risk levels."
    },
}
