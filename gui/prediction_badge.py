# gui/prediction_badge.py
"""
Floating ML prediction badge drawn directly on the chart canvas.
Painted in ChartView.paintEvent — top-right corner.
Shows compact version: direction arrow + probability + confidence dot.
"""

import math
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QLinearGradient, QBrush
from PyQt6.QtCore import QRect, Qt, QPoint

from ml.predictor import Prediction


def draw_prediction_badge(painter: QPainter, rect: QRect, pred: Prediction):
    """
    Draw prediction badge on chart.
    Call from ChartView.paintEvent after all chart elements are drawn.

    rect: full widget rect (painter coordinate space)
    pred: latest Prediction object
    """
    if pred is None:
        return

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Badge position: top-right, 12px margin
    bw = 168
    bh = 72
    bx = rect.width() - bw - 12
    by = 12

    badge_rect = QRect(bx, by, bw, bh)

    # ── Background ────────────────────────────────────────────────────────────
    bg = QColor(10, 14, 26, 210)
    painter.setPen(QPen(QColor(26, 42, 58, 255), 1))
    painter.setBrush(QBrush(bg))
    painter.drawRoundedRect(badge_rect, 8, 8)

    if not pred.ready:
        # Show waiting state
        painter.setPen(QPen(QColor(80, 80, 100), 1))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(badge_rect.adjusted(8, 0, -4, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         pred.message or "ML: Collecting data...")
        painter.restore()
        return

    # ── Border colour based on direction ─────────────────────────────────────
    if pred.direction == "UP":
        border_color = QColor("#00c896")
        dir_color    = QColor("#00c896")
        arrow        = "▲"
    elif pred.direction == "DOWN":
        border_color = QColor("#ff5252")
        dir_color    = QColor("#ff5252")
        arrow        = "▼"
    else:
        border_color = QColor("#555555")
        dir_color    = QColor("#888888")
        arrow        = "●"

    painter.setPen(QPen(border_color, 1))
    painter.setBrush(QBrush(bg))
    painter.drawRoundedRect(badge_rect, 8, 8)

    # ── Left accent bar ───────────────────────────────────────────────────────
    accent_rect = QRect(bx, by + 10, 3, bh - 20)
    painter.fillRect(accent_rect, border_color)

    # ── Row 1: Label ──────────────────────────────────────────────────────────
    painter.setPen(QPen(QColor(74, 158, 255), 1))
    painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
    painter.drawText(QRect(bx + 10, by + 6, bw - 14, 14),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     "ML PREDICTION")

    # ── Row 2: Direction arrow + probability ──────────────────────────────────
    painter.setPen(QPen(dir_color, 1))
    painter.setFont(QFont("Consolas", 16, QFont.Weight.Bold))
    painter.drawText(QRect(bx + 10, by + 20, 28, 26),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     arrow)

    painter.setPen(QPen(QColor(255, 255, 255), 1))
    painter.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
    painter.drawText(QRect(bx + 36, by + 20, 80, 26),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     f"{pred.probability * 100:.1f}%")

    # ── Row 3: Confidence dot + label + model agreement ───────────────────────
    conf_colors = {"High": QColor("#00c896"), "Medium": QColor("#ffb74d"),
                   "Low": QColor("#ff5252")}
    dot_color = conf_colors.get(pred.confidence, QColor("#555"))

    painter.setBrush(QBrush(dot_color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPoint(bx + 14, by + 54), 4, 4)

    painter.setPen(QPen(dot_color, 1))
    painter.setFont(QFont("Segoe UI", 8))
    painter.drawText(QRect(bx + 22, by + 46, 80, 16),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     f"{pred.confidence} confidence")

    # Model agreement indicator (far right of row 3)
    if pred.model_agreement:
        painter.setPen(QPen(QColor("#00c896"), 1))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(QRect(bx + 100, by + 46, 60, 16),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                         "✓ agree")
    else:
        painter.setPen(QPen(QColor("#ff9800"), 1))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(QRect(bx + 90, by + 46, 70, 16),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                         "⚠ diverge")

    painter.restore()
