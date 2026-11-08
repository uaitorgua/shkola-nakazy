"""Діалоги редактора документів: пошук і заміна, формула, таблиця, символ, міжрядковий інтервал."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSpinBox, QTextEdit, QVBoxLayout)

from ..ocr.formula import latex_to_unicode


class FindDialog(QDialog):
    def __init__(self, editor) -> None:
        super().__init__(editor)
        self.setWindowTitle("Пошук і заміна")
        self.ed: QTextEdit = editor.edit
        self.find = QLineEdit()
        self.repl = QLineEdit()
        self.case = QCheckBox("Враховувати регістр")
        self.whole = QCheckBox("Лише цілі слова")
        form = QFormLayout(self)
        form.addRow("Знайти:", self.find)
        form.addRow("Замінити на:", self.repl)
        opts = QHBoxLayout()
        opts.addWidget(self.case)
        opts.addWidget(self.whole)
        form.addRow(opts)
        row = QHBoxLayout()
        for text, slot in (("Далі", self._next), ("Назад", self._prev), ("Замінити", self._replace), ("Замінити все", self._all)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        form.addRow(row)
        self.count = QLabel("")
        form.addRow(self.count)
        self.find.returnPressed.connect(self._next)

    def _flags(self, back=False):
        f = QTextDocument.FindFlag(0)
        if self.case.isChecked():
            f |= QTextDocument.FindFlag.FindCaseSensitively
        if self.whole.isChecked():
            f |= QTextDocument.FindFlag.FindWholeWords
        if back:
            f |= QTextDocument.FindFlag.FindBackward
        return f

    def _next(self) -> bool:
        if not self.ed.find(self.find.text(), self._flags()):
            c = self.ed.textCursor()
            c.movePosition(QTextCursor.MoveOperation.Start)
            self.ed.setTextCursor(c)
            ok = self.ed.find(self.find.text(), self._flags())
            self.count.setText("" if ok else "Не знайдено")
            return ok
        return True

    def _prev(self) -> bool:
        return self.ed.find(self.find.text(), self._flags(back=True))

    def _replace(self) -> None:
        c = self.ed.textCursor()
        if c.hasSelection() and c.selectedText().lower() == self.find.text().lower():
            c.insertText(self.repl.text())
        self._next()

    def _all(self) -> None:
        n = 0
        c = self.ed.textCursor()
        c.beginEditBlock()
        c.movePosition(QTextCursor.MoveOperation.Start)
        self.ed.setTextCursor(c)
        while self.ed.find(self.find.text(), self._flags()):
            self.ed.textCursor().insertText(self.repl.text())
            n += 1
        c.endEditBlock()
        self.count.setText(f"Замінено: {n}")


class FormulaDialog(QDialog):
    """Введення формули в LaTeX із попереднім переглядом Unicode-тексту."""

    def __init__(self, parent, latex: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Формула")
        self.ed = QLineEdit(latex)
        self.ed.setPlaceholderText(r"Напр.: x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}")
        self.preview = QLabel()
        self.preview.setStyleSheet("font-size: 14pt; font-style: italic; padding: 6px;")
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.ed.textChanged.connect(self._upd)
        grid = QGridLayout()
        samples = [("x²", "x^{2}"), ("x₁", "x_{1}"), ("a/b", r"\frac{a}{b}"), ("√x", r"\sqrt{x}"), ("±", r"\pm"),
                   ("·", r"\cdot"), ("≤", r"\leq"), ("≥", r"\geq"), ("≠", r"\neq"), ("∞", r"\infty"), ("∑", r"\sum_{i=1}^{n}"),
                   ("∫", r"\int_{a}^{b}"), ("α", r"\alpha"), ("β", r"\beta"), ("π", r"\pi"), ("Δ", r"\Delta"), ("°", r"^{\circ}"), ("→", r"\to")]
        for i, (label, code) in enumerate(samples):
            b = QPushButton(label)
            b.setFixedWidth(40)
            b.clicked.connect(lambda _=False, c=code: self.ed.insert(c))
            grid.addWidget(b, i // 9, i % 9)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Формула (LaTeX):"))
        lay.addWidget(self.ed)
        lay.addLayout(grid)
        lay.addWidget(QLabel("Попередній перегляд:"))
        lay.addWidget(self.preview)
        lay.addWidget(bb)
        self.resize(560, 0)
        self._upd()

    def _upd(self) -> None:
        self.preview.setText(latex_to_unicode(self.ed.text()) or "—")

    def latex(self) -> str:
        return self.ed.text().strip()


class TableDialog(QDialog):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle("Вставити таблицю")
        self.rows, self.cols = QSpinBox(), QSpinBox()
        self.rows.setRange(1, 500)
        self.cols.setRange(1, 60)
        self.rows.setValue(3)
        self.cols.setValue(3)
        self.header = QCheckBox("Перший рядок — заголовок (жирний)")
        self.header.setChecked(True)
        form = QFormLayout(self)
        form.addRow("Рядків:", self.rows)
        form.addRow("Стовпців:", self.cols)
        form.addRow(self.header)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)


SYMBOLS = ("— – … « » „ “ ” ‘ ’ § № © ® ™ ° ± × ÷ ≈ ≠ ≤ ≥ ∞ √ ∑ ∏ ∫ ∂ π α β γ δ ε λ μ σ φ ω Ω Δ "
           "→ ← ↑ ↓ ⇒ ⇔ ∈ ∉ ⊂ ∪ ∩ ∀ ∃ ∠ ⊥ ∥ ′ ″ € ₴ $ £ ¼ ½ ¾ ² ³ ¹ ⁰ ₀ ₁ ₂ ✓ ✗ ★ ☆ • ◦ ▪ ■ □ ● ○ ♦").split()


class SymbolDialog(QDialog):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle("Символ")
        self.chosen = ""
        grid = QGridLayout(self)
        for i, s in enumerate(SYMBOLS):
            b = QPushButton(s)
            b.setFixedSize(34, 30)
            b.clicked.connect(lambda _=False, c=s: self._pick(c))
            grid.addWidget(b, i // 14, i % 14)

    def _pick(self, s: str) -> None:
        self.chosen = s
        self.accept()


class ParagraphDialog(QDialog):
    """Повний діалог абзацу: вирівнювання, відступи ліворуч/праворуч (см), перший рядок (см),
    інтервали перед/після (пт), міжрядковий, крок табуляції (см)."""
    CM = 96 / 2.54

    def __init__(self, parent, bf, tab_px: float) -> None:
        super().__init__(parent)
        self.setWindowTitle("Абзац")
        from PySide6.QtWidgets import QDoubleSpinBox
        self.align = QComboBox()
        self.align.addItems(["Ліворуч", "По центру", "Праворуч", "За шириною"])
        a = bf.alignment()
        self.align.setCurrentIndex(1 if a & Qt.AlignmentFlag.AlignHCenter else 2 if a & Qt.AlignmentFlag.AlignRight
                                   else 3 if a & Qt.AlignmentFlag.AlignJustify else 0)

        def cm(v, lo=-10.0, hi=20.0):
            sp = QDoubleSpinBox()
            sp.setRange(lo, hi)
            sp.setDecimals(2)
            sp.setSingleStep(0.25)
            sp.setSuffix(" см")
            sp.setValue(round(v / self.CM, 2))
            return sp
        self.left = cm(bf.leftMargin(), 0)
        self.right = cm(bf.rightMargin(), 0)
        self.first = cm(bf.textIndent())
        self.before, self.after = QSpinBox(), QSpinBox()
        for sp, v in ((self.before, bf.topMargin()), (self.after, bf.bottomMargin())):
            sp.setRange(0, 200)
            sp.setSuffix(" пт")
            sp.setValue(int(v))
        self.line = QComboBox()
        self.line.addItems(["1,0", "1,15", "1,5", "2,0"])
        lh = bf.lineHeight() / 100 if bf.lineHeightType() == 1 else 1.0
        self.line.setCurrentText({1.0: "1,0", 1.15: "1,15", 1.5: "1,5", 2.0: "2,0"}.get(round(lh, 2), "1,0"))
        self.tab = cm(tab_px, 0.25, 10)
        form = QFormLayout(self)
        form.addRow("Вирівнювання:", self.align)
        form.addRow("Відступ ліворуч:", self.left)
        form.addRow("Відступ праворуч:", self.right)
        form.addRow("Перший рядок:", self.first)
        form.addRow("Перед абзацом:", self.before)
        form.addRow("Після абзацу:", self.after)
        form.addRow("Міжрядковий інтервал:", self.line)
        form.addRow("Крок табуляції (клавіша Tab):", self.tab)
        dstu = QPushButton("За ДСТУ: перший рядок 1 см, інтервал 1,5, за шириною")
        dstu.clicked.connect(lambda: (self.first.setValue(1.0), self.line.setCurrentText("1,5"), self.align.setCurrentIndex(3),
                                      self.left.setValue(0), self.right.setValue(0), self.before.setValue(0), self.after.setValue(0)))
        form.addRow(dstu)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def apply(self, bf) -> float:
        """Повертає крок табуляції у px."""
        bf.setAlignment((Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignRight,
                         Qt.AlignmentFlag.AlignJustify)[self.align.currentIndex()])
        bf.setLeftMargin(self.left.value() * self.CM)
        bf.setRightMargin(self.right.value() * self.CM)
        bf.setTextIndent(self.first.value() * self.CM)
        bf.setTopMargin(self.before.value())
        bf.setBottomMargin(self.after.value())
        bf.setLineHeight(float(self.line.currentText().replace(",", ".")) * 100, 1)
        return self.tab.value() * self.CM


class SpacingDialog(QDialog):
    def __init__(self, parent, line: float = 1.0, before: int = 0, after: int = 0) -> None:
        super().__init__(parent)
        self.setWindowTitle("Абзац")
        self.line = QComboBox()
        self.line.addItems(["1,0", "1,15", "1,5", "2,0"])
        self.line.setCurrentText({1.0: "1,0", 1.15: "1,15", 1.5: "1,5", 2.0: "2,0"}.get(round(line, 2), "1,0"))
        self.before, self.after = QSpinBox(), QSpinBox()
        for sp, v in ((self.before, before), (self.after, after)):
            sp.setRange(0, 120)
            sp.setSuffix(" пт")
            sp.setValue(int(v))
        form = QFormLayout(self)
        form.addRow("Міжрядковий інтервал:", self.line)
        form.addRow("Перед абзацом:", self.before)
        form.addRow("Після абзацу:", self.after)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def line_spacing(self) -> float:
        return float(self.line.currentText().replace(",", "."))
