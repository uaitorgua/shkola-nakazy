"""Параметри сторінки, автоформат за ДСТУ 4163:2020, властивості зображень і таблиць у редакторі документів.

Норми діловодства України (ДСТУ 4163:2020, Типова інструкція з діловодства, постанова КМУ № 55 від 17.01.2018):
A4; береги: ліве 30 мм, праве 10 мм, верхнє та нижнє 20 мм; гарнітура Times New Roman 12–14 пт
(у таблицях 8–12); міжрядковий інтервал 1–1,5; абзацний відступ 10 мм; текст вирівнюється за шириною.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextFrameFormat, QTextLength
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox)

MM = 96 / 25.4          # пікселів у міліметрі при 96 dpi


@dataclass
class PageSetup:
    left: float = 30.0      # мм
    right: float = 10.0
    top: float = 20.0
    bottom: float = 20.0

    def px(self) -> tuple[int, int, int, int]:
        return tuple(round(v * MM) for v in (self.left, self.right, self.top, self.bottom))


DSTU = PageSetup()


class PageSetupDialog(QDialog):
    def __init__(self, parent, setup: PageSetup) -> None:
        super().__init__(parent)
        self.setWindowTitle("Параметри сторінки")
        self.sp = {}
        form = QFormLayout(self)
        form.addRow(QLabel("Аркуш A4 (210 × 297 мм). Береги, мм:"))
        for key, label in (("left", "Ліве"), ("right", "Праве"), ("top", "Верхнє"), ("bottom", "Нижнє")):
            s = QDoubleSpinBox()
            s.setRange(5, 60)
            s.setDecimals(1)
            s.setValue(getattr(setup, key))
            s.setSuffix(" мм")
            self.sp[key] = s
            form.addRow(label + ":", s)
        dstu = QPushButton("За ДСТУ 4163:2020 (30 / 10 / 20 / 20)")
        dstu.clicked.connect(lambda: [self.sp[k].setValue(getattr(DSTU, k)) for k in self.sp])
        form.addRow(dstu)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def setup(self) -> PageSetup:
        return PageSetup(**{k: s.value() for k, s in self.sp.items()})


class DstuDialog(QDialog):
    """Що саме привести до норм."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle("Автоформат за ДСТУ 4163:2020")
        form = QFormLayout(self)
        form.addRow(QLabel("Привести документ до норм діловодства України:"))
        self.margins = QCheckBox("Береги 30 / 10 / 20 / 20 мм")
        self.font = QCheckBox("Шрифт Times New Roman")
        self.size = QComboBox()
        self.size.addItems(["14 пт", "12 пт", "13 пт"])
        self.spacing = QComboBox()
        self.spacing.addItems(["1,5", "1,0", "1,15"])
        self.indent = QCheckBox("Абзацний відступ 10 мм")
        self.justify = QCheckBox("Вирівнювання за шириною")
        self.headings = QCheckBox("Заголовки — жирні, по центру, без відступу")
        self.tables = QCheckBox("Таблиці — 12 пт")
        for c in (self.margins, self.font, self.indent, self.justify, self.headings, self.tables):
            c.setChecked(True)
        form.addRow(self.margins)
        form.addRow(self.font)
        form.addRow("Розмір основного тексту:", self.size)
        form.addRow("Міжрядковий інтервал:", self.spacing)
        form.addRow(self.indent)
        form.addRow(self.justify)
        form.addRow(self.headings)
        form.addRow(self.tables)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def point_size(self) -> int:
        return int(self.size.currentText().split()[0])

    def line_spacing(self) -> float:
        return float(self.spacing.currentText().replace(",", "."))


def apply_page_setup(doc, setup: PageSetup) -> None:
    l, r, t, b = setup.px()
    doc.setDocumentMargin(0)
    ff = doc.rootFrame().frameFormat()
    ff.setLeftMargin(l)
    ff.setRightMargin(r)
    ff.setTopMargin(t)
    ff.setBottomMargin(b)
    doc.rootFrame().setFrameFormat(ff)


def apply_dstu(edit, opts: DstuDialog) -> int:
    """Проходить усі блоки документа. Повертає кількість змінених абзаців."""
    doc = edit.document()
    size = opts.point_size()
    n = 0
    c = QTextCursor(doc)
    c.beginEditBlock()
    block = doc.begin()
    while block.isValid():
        c.setPosition(block.position())
        bf = block.blockFormat()
        in_table = c.currentTable() is not None
        heading = bf.headingLevel() > 0
        cf = QTextCharFormat()
        if opts.font.isChecked():
            cf.setFontFamilies(["Times New Roman"])
        if opts.tables.isChecked() and in_table:
            cf.setFontPointSize(12)
        elif heading:
            cf.setFontPointSize({1: size + 2, 2: size, 3: size}.get(bf.headingLevel(), size))
            if opts.headings.isChecked():
                cf.setFontWeight(QFont.Weight.Bold)
        else:
            cf.setFontPointSize(size)
        c.select(QTextCursor.SelectionType.BlockUnderCursor)
        c.mergeCharFormat(cf)
        nb = QTextBlockFormat()
        nb.setLineHeight(opts.line_spacing() * 100, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        if heading and opts.headings.isChecked():
            nb.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            nb.setTextIndent(0)
            nb.setTopMargin(12)
            nb.setBottomMargin(6)
        elif not in_table and block.textList() is None:
            if opts.indent.isChecked():
                nb.setTextIndent(10 * MM)
            if opts.justify.isChecked():
                nb.setAlignment(Qt.AlignmentFlag.AlignJustify)
            nb.setTopMargin(0)
            nb.setBottomMargin(0)
        c.mergeBlockFormat(nb)
        n += 1
        block = block.next()
    c.endEditBlock()
    if opts.margins.isChecked():
        apply_page_setup(doc, DSTU)
    return n


class ImageDialog(QDialog):
    def __init__(self, parent, w: int, h: int, max_w: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Зображення")
        self.ratio = h / w if w else 1
        self.w, self.h = QSpinBox(), QSpinBox()
        self.w.setRange(10, 4000)
        self.h.setRange(10, 4000)
        self.w.setValue(w)
        self.h.setValue(h)
        self.keep = QCheckBox("Зберігати пропорції")
        self.keep.setChecked(True)
        self.w.valueChanged.connect(lambda v: self.keep.isChecked() and self.h.setValue(round(v * self.ratio)))
        self.align = QComboBox()
        self.align.addItems(["Ліворуч", "По центру", "Праворуч"])
        self.align.setCurrentIndex(1)
        fit = QPushButton(f"На всю ширину ({max_w} px)")
        fit.clicked.connect(lambda: self.w.setValue(max_w))
        form = QFormLayout(self)
        form.addRow("Ширина, px:", self.w)
        form.addRow("Висота, px:", self.h)
        form.addRow(self.keep)
        form.addRow(fit)
        form.addRow("Розташування:", self.align)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def alignment(self):
        return (Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignRight)[self.align.currentIndex()]


class TablePropsDialog(QDialog):
    def __init__(self, parent, table) -> None:
        super().__init__(parent)
        self.setWindowTitle("Властивості таблиці")
        self.table = table
        f = table.format()
        self.border = QDoubleSpinBox()
        self.border.setRange(0, 6)
        self.border.setValue(f.border())
        self.padding = QSpinBox()
        self.padding.setRange(0, 30)
        self.padding.setValue(int(f.cellPadding()))
        self.width = QSpinBox()
        self.width.setRange(10, 100)
        self.width.setSuffix(" %")
        self.width.setValue(100)
        self.align = QComboBox()
        self.align.addItems(["Ліворуч", "По центру", "Праворуч"])
        self.align.setCurrentIndex({Qt.AlignmentFlag.AlignLeft: 0, Qt.AlignmentFlag.AlignHCenter: 1,
                                    Qt.AlignmentFlag.AlignRight: 2}.get(f.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask, 0))
        self.cols = []
        form = QFormLayout(self)
        form.addRow("Товщина меж:", self.border)
        form.addRow("Відступ у комірках, px:", self.padding)
        form.addRow("Ширина таблиці:", self.width)
        form.addRow("Розташування:", self.align)
        row = QHBoxLayout()
        for j in range(min(table.columns(), 12)):
            s = QSpinBox()
            s.setRange(1, 100)
            s.setValue(round(100 / table.columns()))
            s.setToolTip(f"Стовпець {j + 1}, % ширини")
            self.cols.append(s)
            row.addWidget(s)
        form.addRow("Ширина стовпців, %:", row)
        self.bg_btn = QPushButton("Заливка виділених комірок…")
        self.bg = None
        self.bg_btn.clicked.connect(self._pick)
        form.addRow(self.bg_btn)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor("#e3f1ec"), self, "Заливка")
        if c.isValid():
            self.bg = c
            self.bg_btn.setText(f"Заливка: {c.name()}")

    def apply(self, cursor: QTextCursor) -> None:
        f = self.table.format()
        f.setBorder(self.border.value())
        f.setCellPadding(self.padding.value())
        f.setWidth(QTextLength(QTextLength.Type.PercentageLength, self.width.value()))
        f.setAlignment((Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignRight)[self.align.currentIndex()])
        if self.cols:
            f.setColumnWidthConstraints([QTextLength(QTextLength.Type.PercentageLength, s.value()) for s in self.cols]
                                        + [QTextLength()] * (self.table.columns() - len(self.cols)))
        self.table.setFormat(f)
        if self.bg is not None:
            from PySide6.QtGui import QTextTableCellFormat
            cells = []
            if cursor.hasComplexSelection():
                r0, nr, c0, nc = cursor.selectedTableCells()
                cells = [self.table.cellAt(r, c) for r in range(r0, r0 + nr) for c in range(c0, c0 + nc)]
            else:
                cells = [self.table.cellAt(cursor)]
            for cell in cells:
                cf = QTextTableCellFormat(cell.format().toTableCellFormat())
                cf.setBackground(self.bg)
                cell.setFormat(cf)
