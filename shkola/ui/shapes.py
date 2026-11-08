"""Фігури для InterText: прямокутник, скруглений, еліпс, трикутник, ромб, стрілка, лінія, зірка, виноска —
малюються QPainter у зображення (вставляються як картинка, тож потрапляють у DOCX/PDF)."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox)

SHAPES = ["Прямокутник", "Скруглений прямокутник", "Еліпс", "Трикутник", "Ромб", "Стрілка →", "Лінія", "Зірка", "Виноска"]


def draw_shape(kind: str, w: int, h: int, fill: str = "#1d7a66", line: str = "#135548", width: int = 3,
               text: str = "", text_color: str = "#ffffff", scale: int = 2) -> QImage:
    """Повертає зображення фігури (scale — надлишкова роздільність для чіткості)."""
    W, H = w * scale, h * scale
    img = QImage(W + 4, H + 4, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(line), width * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(QBrush(QColor(fill)) if kind != "Лінія" else Qt.BrushStyle.NoBrush)
    m = width * scale
    r = QRectF(m, m, W - 2 * m, H - 2 * m)
    cx, cy = r.center().x(), r.center().y()
    if kind == "Прямокутник":
        p.drawRect(r)
    elif kind == "Скруглений прямокутник":
        p.drawRoundedRect(r, min(r.width(), r.height()) * 0.2, min(r.width(), r.height()) * 0.2)
    elif kind == "Еліпс":
        p.drawEllipse(r)
    elif kind == "Трикутник":
        p.drawPolygon(QPolygonF([QPointF(cx, r.top()), QPointF(r.right(), r.bottom()), QPointF(r.left(), r.bottom())]))
    elif kind == "Ромб":
        p.drawPolygon(QPolygonF([QPointF(cx, r.top()), QPointF(r.right(), cy), QPointF(cx, r.bottom()), QPointF(r.left(), cy)]))
    elif kind == "Стрілка →":
        hw = r.height() * 0.3
        hx = r.right() - r.height() * 0.5
        p.drawPolygon(QPolygonF([QPointF(r.left(), cy - hw / 2), QPointF(hx, cy - hw / 2), QPointF(hx, r.top()),
                                 QPointF(r.right(), cy), QPointF(hx, r.bottom()), QPointF(hx, cy + hw / 2),
                                 QPointF(r.left(), cy + hw / 2)]))
    elif kind == "Лінія":
        p.drawLine(QPointF(r.left(), cy), QPointF(r.right(), cy))
    elif kind == "Зірка":
        pts = []
        R, rr = min(r.width(), r.height()) / 2, min(r.width(), r.height()) / 4.6
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rad = R if i % 2 == 0 else rr
            pts.append(QPointF(cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        p.drawPolygon(QPolygonF(pts))
    elif kind == "Виноска":
        body = QRectF(r.left(), r.top(), r.width(), r.height() * 0.75)
        p.drawRoundedRect(body, 12 * scale, 12 * scale)
        p.drawPolygon(QPolygonF([QPointF(r.left() + r.width() * 0.2, body.bottom() - 1), QPointF(r.left() + r.width() * 0.35, body.bottom() - 1),
                                 QPointF(r.left() + r.width() * 0.15, r.bottom())]))
    if text and kind != "Лінія":
        p.setPen(QColor(text_color))
        f = QFont("Segoe UI", max(8, int(min(W, H) / 8 / scale)) * scale // 1)
        f.setPixelSize(max(10 * scale, int(min(W, H) * 0.16)))
        f.setBold(True)
        p.setFont(f)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
    p.end()
    return img.scaled(w + 2, h + 2, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


class ShapeDialog(QDialog):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle("Вставити фігуру")
        self.kind = QComboBox()
        self.kind.addItems(SHAPES)
        self.w, self.h = QSpinBox(), QSpinBox()
        for sp, v in ((self.w, 240), (self.h, 120)):
            sp.setRange(20, 700)
            sp.setValue(v)
            sp.setSuffix(" px")
        self.width = QSpinBox()
        self.width.setRange(0, 12)
        self.width.setValue(3)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Напис усередині (необов'язково)")
        self.fill, self.line, self.tcolor = "#1d7a66", "#135548", "#ffffff"
        self.b_fill = QPushButton("Заливка: " + self.fill)
        self.b_line = QPushButton("Контур: " + self.line)
        self.b_fill.clicked.connect(lambda: self._pick("fill", self.b_fill, "Заливка: "))
        self.b_line.clicked.connect(lambda: self._pick("line", self.b_line, "Контур: "))
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(140)
        form = QFormLayout(self)
        form.addRow("Фігура:", self.kind)
        form.addRow("Ширина:", self.w)
        form.addRow("Висота:", self.h)
        form.addRow("Товщина контуру:", self.width)
        form.addRow(self.b_fill)
        form.addRow(self.b_line)
        form.addRow("Текст:", self.text)
        form.addRow(self.preview)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        for w in (self.kind, self.w, self.h, self.width):
            (w.currentIndexChanged if isinstance(w, QComboBox) else w.valueChanged).connect(lambda *_: self._upd())
        self.text.textChanged.connect(lambda *_: self._upd())
        self._upd()

    def _pick(self, attr, btn, label) -> None:
        c = QColorDialog.getColor(QColor(getattr(self, attr)), self, label)
        if c.isValid():
            setattr(self, attr, c.name())
            btn.setText(label + c.name())
            self._upd()

    def image(self) -> QImage:
        return draw_shape(self.kind.currentText(), self.w.value(), self.h.value(), self.fill, self.line,
                          self.width.value(), self.text.text(), self.tcolor)

    def _upd(self) -> None:
        from PySide6.QtGui import QPixmap
        img = self.image()
        if img.width() > 320:
            img = img.scaledToWidth(320, Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(QPixmap.fromImage(img))
