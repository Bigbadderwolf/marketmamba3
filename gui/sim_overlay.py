# gui/sim_overlay.py
"""
Simulation overlay — draws ghosted candlesticks in the RIGHT half of the
split chart. Uses the SAME price scale as the live candles (p2y_fn) so
both halves are perfectly aligned on the Y axis.

Called from ChartView.paintEvent after live candles are drawn.
"""
from typing import List, Callable
from PyQt6.QtGui import (QPainter, QPen, QColor, QFont, QBrush,
                          QPainterPath, QPolygonF)
from PyQt6.QtCore import Qt, QRectF, QRect

from simulation.sim_engine import SimScenario


def draw_simulation(
    painter:        QPainter,
    widget_rect:    QRect,
    live_candles:   list,
    scenarios:      List[SimScenario],
    padding:        int,
    candle_spacing: float,         # spacing used for LIVE candles
    min_price:      float,
    price_range:    float,
    visible_count:  int,
    # New split-chart params
    split_x:        int   = 0,     # pixel X where sim zone starts
    sim_width:      int   = 0,     # pixel width of sim zone
    chart_height:   int   = 0,
    p2y_fn:         Callable = None,
):
    if not scenarios or not live_candles:
        return
    if split_x <= 0 or sim_width <= 0:
        return

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Clip all sim drawing to the right zone so it never bleeds into live area
    painter.setClipRect(QRect(split_x, padding, sim_width, chart_height))

    # Use provided p2y or build one from min/range
    if p2y_fn is None:
        def p2y_fn(price):
            return padding + (1.0 - (price - min_price) / max(price_range, 1)) * chart_height

    # How many sim candles fit in the right zone?
    # Use the same candle_spacing as live side so candle widths match
    n_fit = max(1, int(sim_width / candle_spacing))

    # Identify best scenario (highest probability)
    best_sc = max(scenarios,
                  key=lambda s: max(getattr(s, 'up_probability', 0.5),
                                    1 - getattr(s, 'up_probability', 0.5)))

    # Draw non-best first (dimmer), then best on top
    ordered = [s for s in scenarios if s is not best_sc] + [best_sc]

    for sc in ordered:
        is_best = (sc is best_sc)
        _draw_ghosted_candles(
            painter, sc, split_x, sim_width, candle_spacing,
            n_fit, p2y_fn, is_best, chart_height, padding
        )

    # Labels at right edge
    for sc in ordered:
        if sc.candles:
            n_shown = min(len(sc.candles), n_fit)
            last_x  = split_x + (n_shown - 0.5) * candle_spacing
            last_y  = p2y_fn(sc.candles[n_shown - 1]["close"])
            is_best = (sc is best_sc)
            _draw_label(painter, sc.name, sc.color, last_x, last_y, is_best)

    # Best-model probability banner
    if best_sc and best_sc.candles:
        _draw_banner(painter, best_sc, split_x, sim_width,
                     candle_spacing, n_fit, p2y_fn, padding)

    painter.restore()


def _draw_ghosted_candles(
    painter, sc, split_x, sim_width, candle_spacing,
    n_fit, p2y_fn, is_best, chart_height, padding,
):
    """Ghost candles: same shape as real candles, reduced opacity, green/red."""
    body_alpha   = 115 if is_best else 55
    wick_alpha   = 95  if is_best else 40
    border_alpha = 150 if is_best else 65
    half_w       = max(1.5, candle_spacing * (0.40 if is_best else 0.32))

    close_pts = []

    for i, candle in enumerate(sc.candles[:n_fit]):
        cx = split_x + (i + 0.5) * candle_spacing

        o_y = p2y_fn(float(candle["open"]))
        c_y = p2y_fn(float(candle["close"]))
        h_y = p2y_fn(float(candle["high"]))
        l_y = p2y_fn(float(candle["low"]))

        bull = float(candle["close"]) >= float(candle["open"])

        if bull:
            body_c   = QColor(0,   185, 155, body_alpha)
            wick_c   = QColor(0,   185, 155, wick_alpha)
            border_c = QColor(0,   210, 175, border_alpha)
        else:
            body_c   = QColor(255,  75,  75, body_alpha)
            wick_c   = QColor(255,  75,  75, wick_alpha)
            border_c = QColor(255, 100, 100, border_alpha)

        # Glow behind best scenario candles
        if is_best:
            glow_c = QColor(sc.color); glow_c.setAlpha(18)
            top_g  = min(o_y, c_y)
            bh_g   = max(1.5, abs(c_y - o_y))
            painter.fillRect(
                QRectF(cx - half_w - 3, top_g - 3, half_w * 2 + 6, bh_g + 6),
                QBrush(glow_c)
            )

        # Wick
        painter.setPen(QPen(wick_c, 1))
        painter.drawLine(int(cx), int(h_y), int(cx), int(l_y))

        # Body
        top_y  = min(o_y, c_y)
        body_h = max(1.0, abs(c_y - o_y))
        painter.fillRect(
            QRectF(cx - half_w, top_y, half_w * 2, body_h),
            QBrush(body_c)
        )

        # Border
        painter.setPen(QPen(border_c, 1.0 if is_best else 0.6))
        painter.drawRect(QRectF(cx - half_w, top_y, half_w * 2, body_h))

        close_pts.append((cx, p2y_fn(float(candle["close"]))))

    # Close-price path line
    if len(close_pts) >= 2:
        line_c = QColor(sc.color)
        line_c.setAlpha(160 if is_best else 65)
        painter.setPen(QPen(line_c, 1.5 if is_best else 0.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(*close_pts[0])
        for pt in close_pts[1:]:
            path.lineTo(*pt)
        painter.drawPath(path)


def _draw_label(painter, name, color, x, y, is_best):
    col = QColor(color); col.setAlpha(255 if is_best else 140)
    painter.setPen(QPen(col, 1))
    painter.setFont(QFont("Segoe UI", 9 if is_best else 8,
                          QFont.Weight.Bold))
    lbl = f"★ {name}" if is_best else name
    fm  = painter.fontMetrics()
    tw  = fm.horizontalAdvance(lbl) + 10
    th  = 18
    bg  = QColor(10, 14, 26, 210)
    painter.fillRect(QRectF(x + 4, y - th // 2, tw, th), bg)
    border_c = QColor(color); border_c.setAlpha(255 if is_best else 100)
    painter.setPen(QPen(border_c, 1.5 if is_best else 0.8))
    painter.drawRect(QRectF(x + 4, y - th // 2, tw, th))
    painter.setPen(QPen(col, 1))
    painter.drawText(int(x) + 8, int(y) + 5, lbl)


def _draw_banner(painter, sc, split_x, sim_width, candle_spacing,
                 n_fit, p2y_fn, padding):
    if not sc.candles:
        return
    n_shown  = min(len(sc.candles), n_fit)
    mid_i    = n_shown // 2
    banner_x = split_x + (mid_i + 0.5) * candle_spacing

    highest  = max(c["high"] for c in sc.candles[:n_shown])
    banner_y = p2y_fn(highest) - 36

    up_prob  = getattr(sc, 'up_probability', 0.5)
    direction = "LONG ▲" if up_prob > 0.5 else "SHORT ▼"
    prob_pct  = max(up_prob, 1 - up_prob) * 100
    text      = f"★  {direction}  {prob_pct:.1f}%"

    col = QColor(sc.color)
    painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    fm  = painter.fontMetrics()
    tw  = fm.horizontalAdvance(text) + 20
    th  = 22
    bx  = max(split_x + 4, banner_x - tw / 2)

    glow = QColor(sc.color); glow.setAlpha(25)
    painter.fillRect(QRectF(bx - 2, banner_y - 2, tw + 4, th + 4), QBrush(glow))
    painter.fillRect(QRectF(bx, banner_y, tw, th), QColor(8, 12, 20, 230))
    border = QColor(sc.color); border.setAlpha(255)
    painter.setPen(QPen(border, 1.5))
    painter.drawRect(QRectF(bx, banner_y, tw, th))
    painter.fillRect(QRectF(bx, banner_y, 3, th), QBrush(border))
    painter.setPen(QPen(col, 1))
    painter.drawText(int(bx) + 8, int(banner_y) + 15, text)

    # Connector to path
    path_y = p2y_fn(sc.candles[mid_i]["close"])
    painter.setPen(QPen(QColor(sc.color).lighter(120), 1, Qt.PenStyle.DotLine))
    painter.drawLine(int(banner_x), int(banner_y + th), int(banner_x), int(path_y))
