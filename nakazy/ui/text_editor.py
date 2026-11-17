"""Простий вбудований редактор тексту наказу (не InterText): аркуш A4 з реквізитами наказу і текстом.

Оформлення за нормами, звіреними з першоджерелами (PLAN.md, розд. 1):
- поля 30 / 10 / 20 / 20 мм, кегль 12–14 пт, Times New Roman – Інструкція МОН № 676, дод. 1 пп. 1–2;
- «НАКАЗ» великими, дата – місце – номер, заголовок «Про…» – дод. 1 п. 3; р. III п. 1 («НАКАЗУЮ:» з нового
  рядка без відступу);
- абзацний відступ 10 мм, розшифрування підпису на 125 мм від лівого поля – ДСТУ 4163:2020 п. 7.7;
- дата ДД.ММ.РРРР – ДСТУ 4163:2020 п. 5.10; підпис «Власне ім'я ПРІЗВИЩЕ» – п. 5.22.
Шапку (бланк, «НАКАЗ», дата/місце/№, заголовок) і підпис показує картка наказу з реквізитів; редагується
лише текст між ними. Відступи сумісні з перетворенням у DOCX (shkola/export/html_docx.py: рівень відступу
0,4 дюйма, абзацний відступ – text-indent у px при 96 dpi).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCharFormat, QTextFrameFormat, QTextLength, QTextListFormat, \
    QTextTableFormat
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QLabel, QMenu, QScrollArea, QSizePolicy, QSpinBox,
    QTextEdit, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

MM = 96 / 25.4                    # px на мм (96 dpi, як у перетворювачі DOCX)
MARGINS = (30, 10, 20, 20)        # ліве, праве, верхнє, нижнє, мм – як export.MARGINS (дод. 1 п. 2)
PAGE_W = 210                      # A4, мм
PARA_MM = 10                      # абзацний відступ, ДСТУ 4163:2020 п. 7.7
SIGN_MM = 125                     # розшифрування підпису, ДСТУ 4163:2020 п. 7.7
INDENT_PX = 0.4 * 96              # крок відступу: 0,4 дюйма (html_docx)


class _AutoEdit(QTextEdit):
    """Текст наказу на аркуші: без власної прокрутки, висота за вмістом (прокручується весь аркуш)."""

    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self.document().setDocumentMargin(0)

    def _fit(self, *_):
        self.setFixedHeight(max(int(self.document().size().height()) + 6, int(40 * MM)))


class TextEditor(QWidget):
    """Панель форматування + аркуш A4: шапка наказу (head), текст (edit), підпис (foot)."""
    changed = Signal()

    def __init__(self, html: str = "", parent=None, font_size: int = 14):
        super().__init__(parent)
        self.font_size = font_size
        font_css = f"font-family: 'Times New Roman'; font-size: {font_size}pt; color: #000;"
        self.edit = _AutoEdit(); self.edit.setAcceptRichText(True)
        doc = self.edit.document()
        doc.setDefaultFont(QFont("Times New Roman", font_size))
        doc.setIndentWidth(INDENT_PX)
        # шрифт наказу задається і стилем: тема програми інакше підміняє шрифт документа
        self.edit.setStyleSheet(f"QTextEdit {{ background: #fff; border: none; padding: 0; margin: 0; {font_css} }}")
        self.head = QWidget(); self.head_l = QVBoxLayout(self.head)
        self.head_l.setContentsMargins(0, 0, 0, int(3 * MM)); self.head_l.setSpacing(0)
        self.foot = QLabel(); self.foot.setTextFormat(Qt.RichText); self.foot.setWordWrap(True)
        self.foot.setStyleSheet(font_css)
        page = QWidget(); page.setObjectName("page")
        page.setFixedWidth(int(PAGE_W * MM))
        page.setStyleSheet("#page { background: #fff; border: 1px solid #c8c8c8; }")
        pl = QVBoxLayout(page); pl.setSpacing(0)
        pl.setContentsMargins(int(MARGINS[0] * MM), int(MARGINS[2] * MM), int(MARGINS[1] * MM), int(MARGINS[3] * MM))
        pl.addWidget(self.head); pl.addWidget(self.edit); pl.addSpacing(int(8 * MM)); pl.addWidget(self.foot)
        pl.addStretch(1)
        page.setMinimumHeight(int(297 * MM))
        self.page = page
        holder = QWidget(); holder.setObjectName("holder"); hl = QVBoxLayout(holder); hl.setContentsMargins(16, 16, 16, 16)
        holder.setStyleSheet("#holder { background: #e9e9e9; }")
        hl.addWidget(page, 0, Qt.AlignHCenter | Qt.AlignTop)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setWidget(holder)
        self.bar = QToolBar(); self.bar.setMovable(False)
        self._actions()
        hint = QLabel(f"Аркуш A4: поля {MARGINS[0]}/{MARGINS[1]}/{MARGINS[2]}/{MARGINS[3]} мм, Times New Roman "
                      f"{font_size} пт, абзацний відступ {PARA_MM} мм (Інструкція МОН № 676, дод. 1; ДСТУ 4163:2020 "
                      "п. 7.7). Шапка й підпис – з реквізитів праворуч.")
        hint.setWordWrap(True); hint.setStyleSheet("color: #666; font-size: 11px")
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
        v.addWidget(self.bar); v.addWidget(self.scroll, 1); v.addWidget(hint)
        self.setHtml(html)
        doc.contentsChanged.connect(self.changed)
        self.edit.cursorPositionChanged.connect(self._sync_bar)

    # шапка й підпис (з реквізитів наказу)
    def set_frame(self, head_widgets: list, foot_html: str):
        while self.head_l.count():
            w = self.head_l.takeAt(0).widget()
            if w:
                w.deleteLater()
        for w in head_widgets:
            self.head_l.addWidget(w)
        self.foot.setText(foot_html)

    # вміст
    def setHtml(self, html: str):
        self.edit.setHtml(html or "")
        self.edit._fit()
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
        self.size = QComboBox(); self.size.addItems(["12", "13", "14"])
        self.size.setToolTip("Розмір шрифту, пт (дод. 1 п. 1: 12–14)")
        self.size.setCurrentText(str(self.font_size))
        self.size.activated.connect(lambda _i: self._char(size=int(self.size.currentText())))
        self.bar.addWidget(self.size)
        self.a_b = self._act("Ж", "Жирний (Ctrl+B)", lambda on: self._char(bold=on), True)
        self.a_i = self._act("К", "Курсив (Ctrl+I)", lambda on: self._char(italic=on), True)
        self.a_u = self._act("Ч", "Підкреслений (Ctrl+U)", lambda on: self._char(under=on), True)
        for a, key, attr in ((self.a_b, "Ctrl+B", "setBold"), (self.a_i, "Ctrl+I", "setItalic"),
                             (self.a_u, "Ctrl+U", "setUnderline")):
            f = a.font(); getattr(f, attr)(True); a.setFont(f); a.setShortcut(key)
        self.bar.addSeparator()
        self.aligns = {}
        for text, tip, al in (("≡←", "Ліворуч", Qt.AlignLeft), ("≡↔", "По центру", Qt.AlignHCenter),
                              ("≡→", "Праворуч", Qt.AlignRight), ("≡≡", "За шириною", Qt.AlignJustify)):
            self.aligns[al] = self._act(text, tip, lambda _=False, al=al: self.edit.setAlignment(al), True)
        self.bar.addSeparator()
        self.a_first = self._act(f"¶ {PARA_MM} мм", f"Абзацний відступ {PARA_MM} мм (ДСТУ 4163:2020 п. 7.7)",
                                 self._first_line, True)
        self._act("⇤", "Зменшити відступ", lambda: self._indent(-1))
        self._act("⇥", "Збільшити відступ", lambda: self._indent(1))
        self._act("1.", "Нумерований список", lambda: self._list(QTextListFormat.ListDecimal))
        self._act("•", "Маркований список", lambda: self._list(QTextListFormat.ListDisc))
        self.bar.addSeparator()
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
        c = self.edit.textCursor(); b = QTextBlockFormat(); b.setTextIndent(PARA_MM * MM if on else 0)
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
