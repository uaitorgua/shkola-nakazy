"""Графіки для InterTab: стовпчикова, горизонтальна, лінійна, кругова — з виділеного діапазону.
Малюються QPainter (попередній перегляд, PNG, вставка в InterText), а в XLSX зберігаються як справжні
діаграми Excel (openpyxl.chart)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton)

from .sheet_model import col_letters

TYPES = ["Стовпчикова", "Горизонтальна", "Лінійна", "Кругова"]
PALETTE = ["#1d7a66", "#f0b14a", "#2b5fa8", "#b45309", "#7b3fa0", "#15803d", "#b91c1c", "#5d6670"]


@dataclass
class ChartSpec:
    kind: str = "Стовпчикова"
    title: str = ""
    r0: int = 0
    c0: int = 0
    r1: int = 0
    c1: int = 0
    header_row: bool = True       # перший рядок — назви рядів
    label_col: bool = True        # перший стовпець — підписи категорій
    anchor: str = "H2"            # комірка прив'язки в XLSX
    image: QImage | None = field(default=None, repr=False)


def extract(sheet, spec: ChartSpec):
    """→ (категорії, [(назва ряду, [значення])])."""
    rows = list(range(spec.r0, spec.r1 + 1))
    cols = list(range(spec.c0, spec.c1 + 1))
    names = {}
    if spec.header_row and rows:
        names = {c: str(sheet.raw.get((rows[0], c), "") or col_letters(c)) for c in cols}
        rows = rows[1:]
    cats = []
    if spec.label_col and cols:
        cats = [str(sheet.raw.get((r, cols[0]), "") or r + 1) for r in rows]
        cols = cols[1:]
    else:
        cats = [str(r + 1) for r in rows]
    series = []
    for c in cols:
        vals = []
        for r in rows:
            v = sheet.value(r, c)
            vals.append(float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0)
        series.append((names.get(c, col_letters(c)), vals))
    return cats, series


def render(cats: list[str], series: list, kind: str, title: str = "", w: int = 640, h: int = 400) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.white)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    top = 16
    if title:
        f = QFont("Segoe UI", 12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#1b1f23"))
        p.drawText(QRectF(0, 6, w, 24), Qt.AlignmentFlag.AlignCenter, title)
        top = 36
    p.setFont(QFont("Segoe UI", 9))
    legend_h = 22 if len(series) > 1 or kind == "Кругова" else 0
    plot = QRectF(56, top + 8, w - 72, h - top - 44 - legend_h)
    if kind == "Кругова":
        vals = series[0][1] if series else []
        total = sum(v for v in vals if v > 0) or 1
        R = min(plot.width(), plot.height()) / 2 - 10
        c = plot.center()
        ang = 90 * 16
        for i, v in enumerate(vals):
            if v <= 0:
                continue
            span = -int(v / total * 360 * 16)
            p.setBrush(QBrush(QColor(PALETTE[i % len(PALETTE)])))
            p.setPen(QPen(Qt.GlobalColor.white, 2))
            p.drawPie(QRectF(c.x() - R, c.y() - R, 2 * R, 2 * R), ang, span)
            mid = math.radians((ang + span / 2) / 16)
            p.setPen(QColor("#1b1f23"))
            p.drawText(QRectF(c.x() + R * 0.62 * math.cos(mid) - 30, c.y() - R * 0.62 * math.sin(mid) - 10, 60, 20),
                       Qt.AlignmentFlag.AlignCenter, f"{v / total * 100:.0f} %")
            ang += span
        # легенда — категорії
        x = 56
        for i, cat in enumerate(cats):
            p.setBrush(QBrush(QColor(PALETTE[i % len(PALETTE)])))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(x, h - 20, 12, 12))
            p.setPen(QColor("#1b1f23"))
            p.drawText(QRectF(x + 16, h - 24, 140, 20), Qt.AlignmentFlag.AlignVCenter, cat)
            x += 20 + min(140, 8 * len(cat) + 10)
        p.end()
        return img
    vmax = max((v for _, vals in series for v in vals), default=1.0)
    vmin = min((v for _, vals in series for v in vals), default=0.0)
    vmin = min(0.0, vmin)
    vmax = vmax if vmax > vmin else vmin + 1
    # сітка та вісь
    p.setPen(QPen(QColor("#d3dbd8"), 1))
    steps = 5
    for i in range(steps + 1):
        v = vmin + (vmax - vmin) * i / steps
        y = plot.bottom() - (v - vmin) / (vmax - vmin) * plot.height()
        if kind == "Горизонтальна":
            x = plot.left() + (v - vmin) / (vmax - vmin) * plot.width()
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            p.setPen(QColor("#5d6670"))
            p.drawText(QRectF(x - 30, plot.bottom() + 4, 60, 16), Qt.AlignmentFlag.AlignCenter, f"{v:g}")
            p.setPen(QPen(QColor("#d3dbd8"), 1))
        else:
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor("#5d6670"))
            p.drawText(QRectF(0, y - 8, plot.left() - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{v:g}")
            p.setPen(QPen(QColor("#d3dbd8"), 1))
    n, m = max(1, len(cats)), max(1, len(series))
    if kind == "Горизонтальна":
        band = plot.height() / n
        bar = band * 0.7 / m
        for i, cat in enumerate(cats):
            y0 = plot.top() + i * band + band * 0.15
            for j, (name, vals) in enumerate(series):
                v = vals[i] if i < len(vals) else 0
                x0 = plot.left() + (0 - vmin) / (vmax - vmin) * plot.width()
                x1 = plot.left() + (v - vmin) / (vmax - vmin) * plot.width()
                p.setBrush(QBrush(QColor(PALETTE[j % len(PALETTE)])))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(QRectF(min(x0, x1), y0 + j * bar, abs(x1 - x0), bar - 1))
            p.setPen(QColor("#1b1f23"))
            p.drawText(QRectF(0, plot.top() + i * band, plot.left() - 6, band), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, cat[:12])
    else:
        band = plot.width() / n
        for i, cat in enumerate(cats):
            p.setPen(QColor("#1b1f23"))
            p.drawText(QRectF(plot.left() + i * band, plot.bottom() + 4, band, 18), Qt.AlignmentFlag.AlignCenter, cat[:14])
        if kind == "Стовпчикова":
            bar = band * 0.7 / m
            for j, (name, vals) in enumerate(series):
                for i in range(n):
                    v = vals[i] if i < len(vals) else 0
                    y0 = plot.bottom() - (0 - vmin) / (vmax - vmin) * plot.height()
                    y1 = plot.bottom() - (v - vmin) / (vmax - vmin) * plot.height()
                    p.setBrush(QBrush(QColor(PALETTE[j % len(PALETTE)])))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawRect(QRectF(plot.left() + i * band + band * 0.15 + j * bar, min(y0, y1), bar - 1, abs(y1 - y0)))
        else:
            for j, (name, vals) in enumerate(series):
                pts = [QPointF(plot.left() + (i + 0.5) * band, plot.bottom() - ((vals[i] if i < len(vals) else 0) - vmin) / (vmax - vmin) * plot.height())
                       for i in range(n)]
                p.setPen(QPen(QColor(PALETTE[j % len(PALETTE)]), 2.5))
                for a, b in zip(pts, pts[1:]):
                    p.drawLine(a, b)
                p.setBrush(QBrush(QColor(PALETTE[j % len(PALETTE)])))
                for pt in pts:
                    p.drawEllipse(pt, 3.5, 3.5)
    p.setPen(QPen(QColor("#5d6670"), 1))
    p.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))
    p.drawLine(QPointF(plot.left(), plot.top()), QPointF(plot.left(), plot.bottom()))
    if legend_h:
        x = 56
        for j, (name, _) in enumerate(series):
            p.setBrush(QBrush(QColor(PALETTE[j % len(PALETTE)])))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(x, h - 18, 12, 12))
            p.setPen(QColor("#1b1f23"))
            p.drawText(QRectF(x + 16, h - 22, 160, 20), Qt.AlignmentFlag.AlignVCenter, name)
            x += 20 + min(160, 8 * len(name) + 10)
    p.end()
    return img


def add_xlsx_chart(ws, spec: ChartSpec) -> None:
    """Справжня діаграма Excel у аркуші openpyxl."""
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    rows = (spec.r0 + 1, spec.r1 + 1)
    cols = (spec.c0 + 1, spec.c1 + 1)
    data_min_col = cols[0] + (1 if spec.label_col else 0)
    if data_min_col > cols[1]:
        return
    if spec.kind == "Кругова":
        ch = PieChart()
    elif spec.kind == "Лінійна":
        ch = LineChart()
    else:
        ch = BarChart()
        ch.type = "bar" if spec.kind == "Горизонтальна" else "col"
    ch.title = spec.title or None
    data = Reference(ws, min_col=data_min_col, max_col=cols[1], min_row=rows[0], max_row=rows[1])
    ch.add_data(data, titles_from_data=spec.header_row)
    if spec.label_col:
        cats = Reference(ws, min_col=cols[0], min_row=rows[0] + (1 if spec.header_row else 0), max_row=rows[1])
        ch.set_categories(cats)
    ch.width, ch.height = 16, 9
    ws.add_chart(ch, spec.anchor)


class ChartDialog(QDialog):
    def __init__(self, parent, sheet, spec: ChartSpec) -> None:
        super().__init__(parent)
        self.setWindowTitle("Вставити графік")
        self.sheet, self.spec = sheet, spec
        self.kind = QComboBox()
        self.kind.addItems(TYPES)
        self.kind.setCurrentText(spec.kind)
        self.title = QLineEdit(spec.title)
        self.title.setPlaceholderText("Назва графіка")
        self.rng = QLabel(f"Діапазон: {col_letters(spec.c0)}{spec.r0 + 1}:{col_letters(spec.c1)}{spec.r1 + 1}")
        self.header = QCheckBox("Перший рядок — назви рядів")
        self.header.setChecked(spec.header_row)
        self.labels = QCheckBox("Перший стовпець — підписи категорій")
        self.labels.setChecked(spec.label_col)
        self.preview = QLabel()
        self.preview.setMinimumSize(480, 300)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        save = QPushButton("Зберегти PNG…")
        save.clicked.connect(self._save_png)
        form = QFormLayout(self)
        form.addRow("Тип:", self.kind)
        form.addRow("Назва:", self.title)
        form.addRow(self.rng)
        form.addRow(self.header)
        form.addRow(self.labels)
        form.addRow(self.preview)
        row = QHBoxLayout()
        row.addWidget(save)
        row.addStretch(1)
        form.addRow(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Вставити в аркуш")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        for w in (self.kind.currentIndexChanged, self.title.textChanged, self.header.toggled, self.labels.toggled):
            w.connect(lambda *_: self._upd())
        self._upd()

    def result_spec(self) -> ChartSpec:
        s = self.spec
        s.kind, s.title = self.kind.currentText(), self.title.text()
        s.header_row, s.label_col = self.header.isChecked(), self.labels.isChecked()
        cats, series = extract(self.sheet, s)
        s.image = render(cats, series, s.kind, s.title)
        return s

    def _upd(self) -> None:
        s = self.result_spec()
        self.preview.setPixmap(QPixmap.fromImage(s.image).scaled(480, 300, Qt.AspectRatioMode.KeepAspectRatio,
                                                                 Qt.TransformationMode.SmoothTransformation))

    def _save_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Зберегти графік", "графік.png", "PNG (*.png)")
        if path:
            self.result_spec().image.save(path)
