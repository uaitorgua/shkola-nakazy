"""Простий вбудований редактор тексту наказу (не InterText): форматування, вирівнювання, відступи,
списки, таблиці; сторінка з полями наказу. Повніше редагування – «Відкрити в іншій програмі».

Поля сторінки – як у збереженому наказі (export.MARGINS: ліве 30, праве 10, верхнє 20, нижнє 20 мм,
Інструкція МОН № 676, дод. 1 п. 2). Відступи сумісні з перетворенням у DOCX (shkola/export/html_docx.py:
рівень відступу = 0,4 дюйма, абзацний відступ – text-indent у px при 96 dpi).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextFrameFormat, QTextListFormat, \
    QTextTableFormat, QTextLength
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QTextEdit, QToolBar, QVBoxLayout, QWidget, QLabel,
)

MM = 96 / 25.4                    # px на мм (96 dpi, як у перетворювачі DOCX)
MARGINS = (30, 10, 20, 20)        # ліве, праве, верхнє, нижнє, мм – як export.MARGINS
FIRST_LINE_MM = 12.5              # абзацний відступ 1,25 см
INDENT_PX = 0.4 * 96              # крок відступу: 0,4 дюйма (html_docx)


class _PageEdit(QTextEdit):
    """Сторінка: поля показуються відступом області перегляду (не в документі – інакше Qt загортає текст
    у кореневу таблицю, і DOCX ламається); рядки переносяться на ширині тексту A4 (210 − 30 − 10 мм)."""

    def __init__(self):
        super().__init__()
        self.setViewportMargins(int(MARGINS[0] * MM), int(MARGINS[2] * MM), int(MARGINS[1] * MM), int(MARGINS[3] * MM))
        self.setLineWrapMode(QTextEdit.FixedPixelWidth)
        self.setLineWrapColumnOrWidth(int((210 - MARGINS[0] - MARGINS[1]) * MM))


class TextEditor(QWidget):
    """Текст наказу: панель форматування + сторінка A4 з полями."""
    changed = Signal()

    def __init__(self, html: str = "", parent=None, font_size: int = 14):
        super().__init__(parent)
        self.edit = _PageEdit(); self.edit.setAcceptRichText(True)
        doc = self.edit.document()
        doc.setDefaultFont(QFont("Times New Roman", font_size))
        doc.setIndentWidth(INDENT_PX)
        # шрифт наказу задається і стилем: тема програми інакше підміняє шрифт документа
        self.edit.setStyleSheet("QTextEdit { background: #ffffff; color: #000000; "
                                f"font-family: 'Times New Roman'; font-size: {font_size}pt; }}")
        self.bar = QToolBar(); self.bar.setMovable(False)
        self.font_size = font_size
        self._actions()
        hint = QLabel(f"Поля сторінки: ліве {MARGINS[0]}, праве {MARGINS[1]}, верхнє й нижнє {MARGINS[2]} мм "
                      "(Інструкція МОН № 676, дод. 1 п. 2)")
        hint.setStyleSheet("color: #666; font-size: 11px")
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
        v.addWidget(self.bar); v.addWidget(self.edit, 1); v.addWidget(hint)
        self.setHtml(html)
        doc.contentsChanged.connect(self.changed)
        self.edit.cursorPositionChanged.connect(self._sync_bar)

    # вміст
    def setHtml(self, html: str):
        self.edit.setHtml(html or "")
        self.edit.document().setModified(False)

    def html(self) -> str:
        return self.edit.toHtml()

    def isModified(self) -> bool:
        return self.edit.document().isModified()

    def setModified(self, on: bool):
        self.edit.document().setModified(on)

    def setReadOnly(self, on: bool):
        self.edit.setReadOnly(on); self.bar.setEnabled(not on)

    # панель
    def _act(self, text, tip, slot, checkable=False):
        a = self.bar.addAction(text); a.setToolTip(tip); a.setCheckable(checkable); a.triggered.connect(slot)
        return a

    def _actions(self):
        e = self.edit
        self._act("↶", "Скасувати (Ctrl+Z)", e.undo); self._act("↷", "Повторити (Ctrl+Y)", e.redo)
        self.bar.addSeparator()
        self.size = QComboBox(); self.size.addItems(["12", "13", "14"]); self.size.setToolTip("Розмір шрифту, пт")
        self.size.setCurrentText(str(self.font_size)); self.size.activated.connect(lambda _i: self._char(size=int(self.size.currentText())))
        self.bar.addWidget(self.size)
        self.a_b = self._act("Ж", "Жирний (Ctrl+B)", lambda on: self._char(bold=on), True)
        self.a_i = self._act("К", "Курсив (Ctrl+I)", lambda on: self._char(italic=on), True)
        self.a_u = self._act("Ч", "Підкреслений (Ctrl+U)", lambda on: self._char(under=on), True)
        f = self.a_b.font(); f.setBold(True); self.a_b.setFont(f)
        f = self.a_i.font(); f.setItalic(True); self.a_i.setFont(f)
        f = self.a_u.font(); f.setUnderline(True); self.a_u.setFont(f)
        for a, key in ((self.a_b, "Ctrl+B"), (self.a_i, "Ctrl+I"), (self.a_u, "Ctrl+U")):
            a.setShortcut(key)
        self.bar.addSeparator()
        self.aligns = {}
        for text, tip, al in (("≡←", "Ліворуч", Qt.AlignLeft), ("≡↔", "По центру", Qt.AlignHCenter),
                              ("≡→", "Праворуч", Qt.AlignRight), ("≡≡", "За шириною", Qt.AlignJustify)):
            self.aligns[al] = self._act(text, tip, lambda _=False, al=al: self.edit.setAlignment(al), True)
        self.bar.addSeparator()
        self.a_first = self._act("¶ 1,25", "Абзацний відступ першого рядка 1,25 см", self._first_line, True)
        self._act("⇤", "Зменшити відступ", lambda: self._indent(-1))
        self._act("⇥", "Збільшити відступ", lambda: self._indent(1))
        self._act("1.", "Нумерований список", lambda: self._list(QTextListFormat.ListDecimal))
        self._act("•", "Маркований список", lambda: self._list(QTextListFormat.ListDisc))
        self.bar.addSeparator()
        from PySide6.QtWidgets import QMenu, QToolButton
        tb = QToolButton(); tb.setText("Таблиця"); tb.setToolTip("Таблиця: вставити, рядки, стовпці, об'єднання")
        tb.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(tb)
        m.addAction("Вставити таблицю…", self.insert_table)
        m.addSeparator()
        m.addAction("Додати рядок нижче", lambda: self._table("row+"))
        m.addAction("Додати стовпець праворуч", lambda: self._table("col+"))
        m.addAction("Видалити рядок", lambda: self._table("row-"))
        m.addAction("Видалити стовпець", lambda: self._table("col-"))
        m.addSeparator()
        m.addAction("Об'єднати виділені клітинки", lambda: self._table("merge"))
        tb.setMenu(m); self.table_menu = m
        self.bar.addWidget(tb)

    def _char(self, bold=None, italic=None, under=None, size=None):
        fmt = QTextCharFormat()
        if bold is not None:
            fmt.setFontWeight(QFont.Bold if bold else QFont.Normal)
        if italic is not None:
            fmt.setFontItalic(italic)
        if under is not None:
            fmt.setFontUnderline(under)
        if size is not None:
            fmt.setFontPointSize(size)
        self.edit.mergeCurrentCharFormat(fmt); self.edit.setFocus()

    def _first_line(self, on):
        c = self.edit.textCursor(); b = QTextBlockFormat(); b.setTextIndent(FIRST_LINE_MM * MM if on else 0)
        c.mergeBlockFormat(b)

    def _indent(self, step):
        c = self.edit.textCursor(); b = c.blockFormat(); b.setIndent(max(0, b.indent() + step)); c.setBlockFormat(b)

    def _list(self, style):
        c = self.edit.textCursor()
        if c.currentList() and c.currentList().format().style() == style:  # повторне натискання – прибрати список
            lst = c.currentList(); lst.remove(c.block())
            b = c.blockFormat(); b.setIndent(0); c.setBlockFormat(b); return
        f = QTextListFormat(); f.setStyle(style); c.createList(f)

    def insert_table(self, rows: int | None = None, cols: int | None = None):
        if rows is None or cols is None:
            d = QDialog(self); d.setWindowTitle("Таблиця"); fl = QFormLayout(d)
            r = QSpinBox(); r.setRange(1, 100); r.setValue(3); c = QSpinBox(); c.setRange(1, 20); c.setValue(3)
            fl.addRow("Рядків", r); fl.addRow("Стовпців", c)
            bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            bb.accepted.connect(d.accept); bb.rejected.connect(d.reject); fl.addRow(bb)
            if not d.exec():
                return
            rows, cols = r.value(), c.value()
        f = QTextTableFormat()
        f.setBorder(1); f.setBorderStyle(QTextFrameFormat.BorderStyle_Solid); f.setCellSpacing(0); f.setCellPadding(4)
        f.setBorderCollapse(True); f.setWidth(QTextLength(QTextLength.PercentageLength, 100))
        return self.edit.textCursor().insertTable(rows, cols, f)

    def _table(self, op):
        c = self.edit.textCursor(); t = c.currentTable()
        if t is None:
            return
        cell = t.cellAt(c)
        if op == "row+":
            t.insertRows(cell.row() + 1, 1)
        elif op == "col+":
            t.insertColumns(cell.column() + 1, 1)
        elif op == "row-":
            t.removeRows(cell.row(), 1) if t.rows() > 1 else c.deletePreviousChar()
        elif op == "col-" and t.columns() > 1:
            t.removeColumns(cell.column(), 1)
        elif op == "merge":
            t.mergeCells(c)

    def _sync_bar(self):
        f = self.edit.currentCharFormat()
        self.a_b.setChecked(f.fontWeight() >= QFont.Bold); self.a_i.setChecked(f.fontItalic())
        self.a_u.setChecked(f.fontUnderline())
        al = self.edit.alignment()
        for a_al, a in self.aligns.items():
            a.setChecked(bool(al & a_al) if a_al != Qt.AlignLeft else not (al & (Qt.AlignHCenter | Qt.AlignRight | Qt.AlignJustify)))
        self.a_first.setChecked(self.edit.textCursor().blockFormat().textIndent() > 0)
        if f.fontPointSize():
            self.size.setCurrentText(str(int(round(f.fontPointSize()))))
