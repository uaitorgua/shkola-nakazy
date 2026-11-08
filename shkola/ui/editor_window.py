"""Редактор документів (WYSIWYG, як Word у простому варіанті): сторінка A4 на сірому тлі, шрифти, розмір,
Ж/К/П/закреслений, верхній/нижній індекс, колір тексту й виділення, вирівнювання, відступи, інтервали, списки,
таблиці (вставка, рядки/стовпці, об'єднання, заголовок), зображення, символи, формули (LaTeX), розрив сторінки,
пошук і заміна, скасувати/повторити, масштаб, лічильник слів, друк; DOCX/PDF/HTML/TXT."""

from __future__ import annotations

import base64
from pathlib import Path

from PySide6.QtCore import QSizeF, Qt, QUrl
from PySide6.QtGui import (QAction, QColor, QFont, QImage, QKeySequence, QPageSize, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextFormat, QTextImageFormat, QTextListFormat, QTextTableFormat)
from PySide6.QtWidgets import (QMenu, QToolButton, QColorDialog, QComboBox, QFileDialog, QFontComboBox, QGraphicsDropShadowEffect,
                               QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox, QScrollArea, QSpinBox,
                               QTextEdit, QToolBar, QVBoxLayout, QWidget)

from ..config import APP_NAME, INTERTEXT
from ..ocr.formula import latex_to_unicode
from .editor_dialogs import FindDialog, FormulaDialog, ParagraphDialog, SpacingDialog, SymbolDialog, TableDialog
from .editor_page import DSTU, DstuDialog, ImageDialog, PageSetup, PageSetupDialog, TablePropsDialog, apply_dstu, apply_page_setup
from .logo import app_icon
from .banner import Banner
from . import icons
from .doc_pages import TEMPLATES, HeaderFooter, HeaderFooterDialog, docx_add_hf, insert_toc, render_pages
from .ribbon import RIBBON_STYLE, Ribbon
from .ruler import Ruler

HEADINGS = ["Звичайний текст", "Заголовок 1", "Заголовок 2", "Заголовок 3"]
HEAD_SIZES = {1: 20, 2: 16, 3: 13}
PAGE_W, PAGE_H = 794, 1123          # A4 при 96 dpi
LIST_STYLES = [("• Маркований", QTextListFormat.Style.ListDisc), ("◦ Кружечки", QTextListFormat.Style.ListCircle),
               ("▪ Квадрати", QTextListFormat.Style.ListSquare), ("1. Нумерований", QTextListFormat.Style.ListDecimal),
               ("a. Літери", QTextListFormat.Style.ListLowerAlpha), ("A. Великі літери", QTextListFormat.Style.ListUpperAlpha),
               ("i. Римські", QTextListFormat.Style.ListLowerRoman)]


EDITOR_ICONS = {
    "↶": "undo", "↷": "redo", "Ж": "bold", "К": "italic", "П": "underline", "abc": "strikethrough", "x²": "superscript",
    "x₂": "subscript", "A": "font", "▇": "highlighter", "Очистити формат": "eraser", "⯇": "align-left", "▣": "align-center",
    "⯈": "align-right", "≡": "align-justify", "¶": "ruler", "⇤": "outdent", "⇥": "indent", "↕ Інтервал": "text-height", "ДСТУ": "stamp",
    "Таблиця": "table", "+ Рядок": "table-rows", "+ Стовпець": "table-cols", "− Рядок": "minus", "− Стовпець": "minus",
    "Об'єднати": "merge", "Роз'єднати": "split", "Таблиця…": "gear", "Зображення…": "image", "Символ…": "symbol",
    "∑ Формула": "formula", "Лінія": "line", "Розрив сторінки": "page-break", "Дата": "calendar", "Пошук": "search",
}


ADAPT_SHOWN: set[str] = set()


def adaptation_notice(parent, origin: str) -> None:
    """Попередження (раз на сеанс): субдодаток не є нативним Word/Excel і адаптує документ."""
    if origin in ADAPT_SHOWN:
        return
    ADAPT_SHOWN.add(origin)
    QMessageBox.information(parent, "Документ адаптовано",
        f"Файл {origin} відкрито з адаптацією під внутрішній формат. InterText та InterTab — не повноцінні офісні пакети, "
        "а засоби для швидкого створення й редагування: при збереженні частина оформлення (складні стилі, макроси, "
        "колонтитули, вбудовані об'єкти, умовне форматування) може бути спрощена або втрачена.\n\n"
        "Для повноцінної роботи зі складними документами користуйтеся офісним пакетом (наприклад, LibreOffice); "
        "радимо зберігати копію оригіналу.")


class PageEdit(QTextEdit):
    """Текстове поле у вигляді аркуша A4 з полями."""

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptRichText(True)
        self.setFrameShape(QTextEdit.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedWidth(PAGE_W)
        self.setMinimumHeight(PAGE_H)
        self.setStyleSheet("QTextEdit { background: white; border: none; }")
        self.setTabChangesFocus(False)
        self.setTabStopDistance(1.25 * 96 / 2.54)
        self.setup = PageSetup()
        self.document().setPageSize(QSizeF(PAGE_W, PAGE_H))
        apply_page_setup(self.document(), self.setup)
        self.document().contentsChanged.connect(self._grow)

    def set_page_setup(self, setup: PageSetup) -> None:
        self.setup = setup
        apply_page_setup(self.document(), setup)
        self._grow()

    def _grow(self) -> None:
        h = int(self.document().size().height())
        pages = max(1, -(-h // PAGE_H))
        self.setFixedHeight(pages * PAGE_H)

    def mouseDoubleClickEvent(self, e) -> None:
        c = self.cursorForPosition(e.position().toPoint())
        c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
        if c.charFormat().isImageFormat():
            self.setTextCursor(c)
            self.window()._image_props()
            return
        super().mouseDoubleClickEvent(e)

    def resource_image(self, name: str) -> QImage | None:
        v = self.document().resource(QTextDocument.ResourceType.ImageResource, QUrl(name))
        return v if isinstance(v, QImage) else (QImage(v) if v is not None else None)


class EditorWindow(QMainWindow):
    def __init__(self, parent=None, html: str = "", title: str = "Документ") -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{title} — {INTERTEXT} · {APP_NAME}")
        self.setWindowIcon(app_icon())
        self.resize(1280, 860)
        self.setStyleSheet(RIBBON_STYLE)
        self.path: Path | None = None
        self._img_n = 0
        self.edit = PageEdit()
        f = QFont("Times New Roman", 12)
        self.edit.setFont(f)
        self.edit.document().setDefaultFont(f)
        self.edit.setCurrentFont(f)
        # м'яка тінь під аркушем A4 — відчуття реального паперу на столі
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.edit.setGraphicsEffect(shadow)
        # аркуш по центру графітового поля з прокруткою
        self.scroll = QScrollArea()
        self.scroll.setObjectName("canvas")
        self.scroll.setWidgetResizable(True)
        holder = QWidget()
        holder.setObjectName("canvas")
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(28, 28, 28, 28)
        hl.addStretch(1)
        hl.addWidget(self.edit, 0, Qt.AlignmentFlag.AlignTop)
        hl.addStretch(1)
        self.scroll.setWidget(holder)
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self.scroll, 1)
        self.setCentralWidget(central)
        self.hf = HeaderFooter()
        self._ribbon()
        self._menu()
        self.ribbon.finish(self.menuBar())
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)
        tl.addWidget(Banner(INTERTEXT, "РЕДАКТОР ДОКУМЕНТІВ · DOCX · PDF · ДРУК · ДСТУ 4163:2020", compact=True))
        tl.addWidget(self.ribbon)
        self.ruler = Ruler()
        tl.addWidget(self.ruler)
        self.setMenuWidget(top)
        self.scroll.horizontalScrollBar().valueChanged.connect(lambda _v: self._sync_ruler())
        self.ruler.indents_changed.connect(self._ruler_indents)
        self.words = QLabel("")
        self.statusBar().addPermanentWidget(self.words)
        self.edit.textChanged.connect(self._count)
        self.edit.cursorPositionChanged.connect(self._sync_toolbar)
        self.edit.currentCharFormatChanged.connect(lambda _f: self._sync_toolbar())
        if html:
            self.set_html(html)
        self._count()
        self.statusBar().showMessage("Готово")

    # ---------- вміст ----------
    def set_html(self, html: str) -> None:
        self.edit.setHtml(html)
        self.edit.set_page_setup(self.edit.setup)
        self.edit.document().setModified(False)

    def html(self) -> str:
        return self.edit.toHtml()

    def _sync_ruler(self) -> None:
        if not hasattr(self, "ruler"):
            return
        x = self.edit.mapTo(self, self.edit.rect().topLeft()).x() - self.ruler.mapTo(self, self.ruler.rect().topLeft()).x()
        l, r, _, _ = self.edit.setup.px()
        self.ruler.set_page(x, self.edit.width(), l, r)
        bf = self.edit.textCursor().blockFormat()
        self.ruler.set_indents(bf.textIndent(), bf.leftMargin())

    def _ruler_indents(self, first: float, indent: float) -> None:
        c = self.edit.textCursor()
        bf = c.blockFormat()
        bf.setTextIndent(first)
        bf.setLeftMargin(indent)
        c.mergeBlockFormat(bf)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._sync_ruler()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._sync_ruler()

    def _count(self) -> None:
        t = self.edit.toPlainText()
        self.words.setText(f"Слів: {len(t.split())}   Символів: {len(t)}   Сторінок: {max(1, self.edit.document().pageCount())}")

    # ---------- інтерфейс ----------
    def _act(self, text, slot, key=None, checkable=False, tip=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if key:
            a.setShortcut(QKeySequence(key))
        a.setCheckable(checkable)
        a.setToolTip(tip or text)
        return a

    def _ribbon(self) -> None:
        """Власна стрічка InterText: Текст / Додати / Сторінка / Таблиця / Перевірка / Вигляд."""
        from PySide6.QtWidgets import QPushButton
        rb = Ribbon(self)
        self.ribbon = rb
        A = QTextCharFormat.VerticalAlignment
        # ---- Основне ----
        home = rb.tab("Текст")
        g = home.group("Обмін")
        g.big("Вставити", "paste", self.edit.paste, "Ctrl+V")
        g.column(g.action("Вирізати", "cut", self.edit.cut, "Ctrl+X"), g.action("Копіювати", "copy", self.edit.copy, "Ctrl+C"),
                 g.action("Без формату", "eraser", self._paste_plain, "Ctrl+Shift+V", tip="Вставити без форматування"))
        g = home.group("Кроки")
        g.column(g.action("Скасувати", "undo", self.edit.undo, "Ctrl+Z"), g.action("Повторити", "redo", self.edit.redo, "Ctrl+Y"))
        g = home.group("Шрифт")
        self.cb_font = QFontComboBox()
        self.cb_font.setCurrentFont(QFont("Times New Roman"))
        self.cb_font.setToolTip("Шрифт")
        self.cb_font.setFixedWidth(170)
        self.cb_font.currentFontChanged.connect(lambda f: self.edit.setFontFamily(f.family()))
        self.sp_size = QSpinBox()
        self.sp_size.setRange(6, 96)
        self.sp_size.setValue(12)
        self.sp_size.setToolTip("Розмір шрифту")
        self.sp_size.valueChanged.connect(lambda v: self.edit.setFontPointSize(v))
        fr = QWidget()
        frl = QHBoxLayout(fr)
        frl.setContentsMargins(0, 0, 0, 0)
        frl.setSpacing(2)
        frl.addWidget(self.cb_font)
        frl.addWidget(self.sp_size)
        self.a_bold = g.action("Жирний", "bold", self._bold, "Ctrl+B", True)
        self.a_italic = g.action("Курсив", "italic", self._italic, "Ctrl+I", True)
        self.a_under = g.action("Підкреслений", "underline", self._underline, "Ctrl+U", True)
        self.a_strike = g.action("Закреслений", "strikethrough", self._strike, None, True)
        self.a_sup = g.action("Верхній індекс", "superscript", lambda: self._script(A.AlignSuperScript), "Ctrl+Shift+=", True)
        self.a_sub = g.action("Нижній індекс", "subscript", lambda: self._script(A.AlignSubScript), "Ctrl+=", True)
        a_bigger = g.action("Більший", "zoom-in", lambda: self.sp_size.setValue(self.sp_size.value() + 1), tip="Збільшити шрифт")
        a_smaller = g.action("Менший", "zoom-out", lambda: self.sp_size.setValue(max(6, self.sp_size.value() - 1)), tip="Зменшити шрифт")
        a_color = g.action("Колір тексту", "font", self._text_color)
        a_hl = g.action("Маркер", "highlighter", self._highlight, tip="Колір виділення")
        a_clear = g.action("Очистити формат", "eraser", self._clear_format, "Ctrl+Space")
        row2 = QWidget()
        r2 = QHBoxLayout(row2)
        r2.setContentsMargins(0, 0, 0, 0)
        r2.setSpacing(1)
        for a in (self.a_bold, self.a_italic, self.a_under, self.a_strike, self.a_sup, self.a_sub, a_bigger, a_smaller, a_color, a_hl, a_clear):
            r2.addWidget(g._button(a, False, False))
        g.vwidgets(fr, row2)
        g = home.group("Абзац")
        self.cb_list = QComboBox()
        self.cb_list.addItem("Список…")
        for name, _ in LIST_STYLES:
            self.cb_list.addItem(name)
        self.cb_list.setToolTip("Марковані й нумеровані списки (повторний вибір — зняти)")
        self.cb_list.activated.connect(self._list_chosen)
        self.cb_list.setFixedWidth(130)
        self.a_left = g.action("Ліворуч", "align-left", lambda: self._align(Qt.AlignmentFlag.AlignLeft), "Ctrl+L", True)
        self.a_center = g.action("По центру", "align-center", lambda: self._align(Qt.AlignmentFlag.AlignHCenter), "Ctrl+E", True)
        self.a_right = g.action("Праворуч", "align-right", lambda: self._align(Qt.AlignmentFlag.AlignRight), "Ctrl+R", True)
        self.a_just = g.action("За шириною", "align-justify", lambda: self._align(Qt.AlignmentFlag.AlignJustify), "Ctrl+J", True)
        a_out = g.action("Зменшити відступ", "outdent", lambda: self._indent(-1), "Ctrl+Shift+M")
        a_in = g.action("Збільшити відступ", "indent", lambda: self._indent(1), "Ctrl+M")
        a_sp = g.action("Інтервал", "text-height", self._spacing, tip="Міжрядковий інтервал і відступи абзацу")
        a_para = g.action("Абзац…", "ruler", self._paragraph, "Ctrl+Alt+P", tip="Абзац: відступи, перший рядок, інтервали, табуляція")
        a_ul = g.action("Маркований", "list-ul", lambda: self._list(QTextListFormat.Style.ListDisc))
        a_ol = g.action("Нумерований", "list-ol", lambda: self._list(QTextListFormat.Style.ListDecimal))
        r1w = QWidget()
        r1 = QHBoxLayout(r1w)
        r1.setContentsMargins(0, 0, 0, 0)
        r1.setSpacing(1)
        for a in (a_ul, a_ol):
            r1.addWidget(g._button(a, False, False))
        r1.addWidget(self.cb_list)
        for a in (a_out, a_in):
            r1.addWidget(g._button(a, False, False))
        r2w = QWidget()
        r2 = QHBoxLayout(r2w)
        r2.setContentsMargins(0, 0, 0, 0)
        r2.setSpacing(1)
        for a in (self.a_left, self.a_center, self.a_right, self.a_just, a_sp, a_para):
            r2.addWidget(g._button(a, False, False))
        g.vwidgets(r1w, r2w)
        g = home.group("Вигляд тексту")
        self.cb_style = QComboBox()
        self.cb_style.addItems(HEADINGS)
        self.cb_style.setToolTip("Стиль абзацу")
        self.cb_style.activated.connect(self._set_heading)
        self.cb_style.setFixedWidth(150)
        self.cb_style.hide()
        g.widget(self.cb_style)
        styles = QWidget()
        sl = QHBoxLayout(styles)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(3)
        for i, (label, css) in enumerate((("Звичайний", "font-size: 10pt;"), ("Заголовок 1", "font-size: 12pt; font-weight: 700;"),
                                          ("Заголовок 2", "font-size: 11pt; font-weight: 700;"), ("Заголовок 3", "font-size: 10pt; font-weight: 700;"))):
            b = QPushButton(label)
            b.setToolTip(f"Стиль: {label}")
            b.setStyleSheet(f"QPushButton {{ {css} padding: 4px 6px; min-width: 96px; min-height: 40px; border-radius: 6px; }}")
            b.clicked.connect(lambda _=False, k=i: (self.cb_style.setCurrentIndex(k), self._set_heading(k)))
            sl.addWidget(b)
        g.widget(styles)
        g.big("ДСТУ", "stamp", self._dstu, "Ctrl+Shift+D", tip="Автоформат за ДСТУ 4163:2020")
        g = home.group("Знайти")
        g.column(g.action("Пошук", "search", lambda: FindDialog(self).show(), "Ctrl+F"),
                 g.action("Замінити", "edit", lambda: FindDialog(self).show(), "Ctrl+H"),
                 g.action("Виділити все", "check", self.edit.selectAll, "Ctrl+A"))
        # ---- Вставлення ----
        ins = rb.tab("Додати")
        g = ins.group("Таблиця")
        g.big("Таблиця", "table", self._insert_table, "Ctrl+T")
        g = ins.group("Малюнки")
        g.big("Зображення", "image", self._insert_image, "Ctrl+Shift+I", tip="Вставити зображення з файлу")
        g.big("Фігури", "wand", self._insert_shape, tip="Прямокутник, еліпс, стрілка, лінія, зірка, виноска…")
        g = ins.group("Знаки й формули")
        g.big("Формула", "formula", self._insert_formula, "Ctrl+Shift+F", tip="Вставити/виправити формулу (LaTeX)")
        g.big("Символ", "symbol", self._insert_symbol)
        g = ins.group("Розмітка")
        g.big("Розрив сторінки", "page-break", self._page_break, "Ctrl+Return")
        g = ins.group("Структура")
        g.big("Зміст", "list-ol", self._toc, tip="Зміст за заголовками 1–3 з номерами сторінок")
        b_tpl = g.big("Шаблон", "new", None, tip="Шкільні документи: наказ, протокол, лист, план-конспект, оголошення")
        self._tpl_menu = QMenu(self)
        for name in TEMPLATES:
            self._tpl_menu.addAction(name, lambda n=name: self._template(n))
        for btn in g.findChildren(QToolButton):
            if btn.defaultAction() is b_tpl:
                btn.setMenu(self._tpl_menu)
                btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        g = ins.group("Лінія й дата")
        g.column(g.action("Лінія", "line", lambda: self.edit.insertHtml("<hr/>"), tip="Горизонтальна лінія"),
                 g.action("Дата", "calendar", self._insert_date, tip="Поточна дата"))
        # ---- Макет ----
        lay = rb.tab("Сторінка")
        g = lay.group("Аркуш")
        g.big("Береги", "ruler", self._page_setup, tip="Параметри сторінки (береги)")
        g.big("ДСТУ 4163", "stamp", self._dstu, tip="Автоформат за ДСТУ 4163:2020")
        g = lay.group("Колонтитули")
        g.big("Колонтитули", "file-lines", self._headers, tip="Верхній і нижній колонтитули, номери сторінок")
        g = lay.group("Оформлення документа")
        self.cb_docstyle = QComboBox()
        self.cb_docstyle.setToolTip("Вбудовані й збережені стилі документа")
        self.cb_docstyle.setFixedWidth(170)
        self._refresh_styles()
        g.vwidgets(self.cb_docstyle)
        g.big("Застосувати", "check", self._apply_style, tip="Застосувати обраний стиль до всього документа")
        g.column(g.action("Зберегти стиль…", "save", self._save_style, tip="Зберегти оформлення поточного документа як стиль"),
                 g.action("Завантажити стиль…", "folder-open", self._load_style, tip="Відкрити файл стилю (.json) і застосувати"))
        g = lay.group("Відступи")
        g.big("Абзац…", "text-height", self._paragraph, tip="Відступи, перший рядок, інтервали, табуляція")
        g.column(g.action("Перший рядок 1 см", "indent", lambda: self._first_line(10)),
                 g.action("Без відступу", "outdent", lambda: self._first_line(0)))
        # ---- Таблиця ----
        tt = rb.tab("Таблиця")
        g = tt.group("Рядки й стовпці")
        g.grid([[g.action("Рядок після", "table-rows", self._add_row, tip="Додати рядок після поточного"),
                 g.action("Стовпець після", "table-cols", self._add_col, tip="Додати стовпець після поточного")],
                [g.action("Видалити рядок", "minus", self._del_row), g.action("Видалити стовпець", "minus", self._del_col)]])
        g = tt.group("Комірки")
        g.big("Об'єднати", "merge", self._merge_cells, tip="Об'єднати виділені комірки")
        g.big("Роз'єднати", "split", self._split_cell)
        g = tt.group("Налаштування")
        g.big("Таблиця…", "gear", self._table_props, tip="Межі, ширина стовпців, заливка")
        g.big("Зображення…", "image", self._image_props, tip="Розмір і розташування зображення")
        # ---- Перевірка ----
        rv = rb.tab("Перевірка")
        g = rv.group("Пошук у тексті")
        g.big("Знайти й замінити", "search", lambda: FindDialog(self).show())
        g = rv.group("Обсяг")
        g.big("Статистика", "info", lambda: (self._count(), QMessageBox.information(self, "Статистика", self.words.text())),
              tip="Слова, символи, сторінки")
        g = rv.group("Оформлення")
        g.big("Перевірити ДСТУ", "stamp", self._dstu, tip="Привести документ до ДСТУ 4163:2020")
        # ---- Подання ----
        view = rb.tab("Вигляд")
        g = view.group("Масштаб")
        self.cb_zoom = QComboBox()
        self.cb_zoom.addItems(["75 %", "100 %", "125 %", "150 %"])
        self.cb_zoom.setCurrentIndex(1)
        self.cb_zoom.currentIndexChanged.connect(self._zoom)
        g.widget(self.cb_zoom)
        g = view.group("Папір і PDF")
        g.big("Перегляд", "eye", self._preview, tip="Попередній перегляд друку")
        g.big("Друк", "print", self._print, "Ctrl+P")
        g.big("PDF", "file-pdf", lambda: self.save_as("pdf"), tip="Зберегти як PDF")

    def _menu(self) -> None:
        m = self.menuBar().addMenu("Файл")
        m.addAction(self._act("Новий", self._new, "Ctrl+N"))
        self._tpl_menu.setTitle("Новий за шаблоном")
        m.addMenu(self._tpl_menu)
        m.addAction(self._act("Відкрити… (DOCX, HTML, TXT)", self.open_file, "Ctrl+O"))
        m.addAction(self._act("Зберегти", self.save, "Ctrl+S"))
        m.addAction(self._act("Зберегти як DOCX…", lambda: self.save_as("docx"), "Ctrl+Shift+S"))
        m.addAction(self._act("Зберегти як PDF…", lambda: self.save_as("pdf")))
        m.addAction(self._act("Зберегти як HTML…", lambda: self.save_as("html")))
        m.addAction(self._act("Зберегти як TXT…", lambda: self.save_as("txt")))
        m.addSeparator()
        m.addAction(self._act("Попередній перегляд…", self._preview))
        m.addAction(self._act("Друк…", self._print, "Ctrl+P"))
        m.addSeparator()
        m.addAction(self._act("Закрити", self.close, "Ctrl+W"))
        fm = self.menuBar().addMenu("Формат")
        fm.addAction(self._act("Параметри сторінки (береги)…", self._page_setup))
        fm.addAction(self._act("Автоформат за ДСТУ 4163:2020…", self._dstu, "Ctrl+Shift+D",
                               tip="Шрифт, розмір, береги, інтервал, абзацний відступ за нормами діловодства"))
        fm.addAction(self._act("Зберегти стиль документа…", self._save_style))
        fm.addAction(self._act("Завантажити стиль документа…", self._load_style))
        fm.addSeparator()
        fm.addAction(self._act("Абзац… (відступи, інтервали, табуляція)", self._paragraph, "Ctrl+Alt+P"))
        fm.addAction(self._act("Абзац: інтервали…", self._spacing))
        fm.addAction(self._act("Перший рядок: відступ 10 мм", lambda: self._first_line(10)))
        fm.addAction(self._act("Перший рядок: без відступу", lambda: self._first_line(0)))
        fm.addSeparator()
        fm.addAction(self._act("Властивості таблиці…", self._table_props))
        fm.addAction(self._act("Властивості зображення…", self._image_props))
        e = self.menuBar().addMenu("Правка")
        e.addAction(self._act("Скасувати", self.edit.undo, "Ctrl+Z"))
        e.addAction(self._act("Повторити", self.edit.redo, "Ctrl+Y"))
        e.addSeparator()
        e.addAction(self._act("Вирізати", self.edit.cut, "Ctrl+X"))
        e.addAction(self._act("Копіювати", self.edit.copy, "Ctrl+C"))
        e.addAction(self._act("Вставити", self.edit.paste, "Ctrl+V"))
        e.addAction(self._act("Вставити без форматування", self._paste_plain, "Ctrl+Shift+V"))
        e.addAction(self._act("Виділити все", self.edit.selectAll, "Ctrl+A"))
        e.addSeparator()
        e.addAction(self._act("Пошук і заміна…", lambda: FindDialog(self).show(), "Ctrl+H"))
        e.addAction(self._act("ВЕЛИКІ літери", lambda: self._case(str.upper)))
        e.addAction(self._act("малі літери", lambda: self._case(str.lower)))

    # ---------- символи ----------
    def _bold(self) -> None:
        self.edit.setFontWeight(QFont.Weight.Bold if self.a_bold.isChecked() else QFont.Weight.Normal)

    def _italic(self) -> None:
        self.edit.setFontItalic(self.a_italic.isChecked())

    def _underline(self) -> None:
        self.edit.setFontUnderline(self.a_under.isChecked())

    def _strike(self) -> None:
        f = QTextCharFormat()
        f.setFontStrikeOut(self.a_strike.isChecked())
        self.edit.mergeCurrentCharFormat(f)

    def _script(self, where) -> None:
        f = QTextCharFormat()
        cur = self.edit.currentCharFormat().verticalAlignment()
        f.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal if cur == where else where)
        self.edit.mergeCurrentCharFormat(f)

    def _text_color(self) -> None:
        c = QColorDialog.getColor(self.edit.textColor(), self, "Колір тексту")
        if c.isValid():
            self.edit.setTextColor(c)

    def _highlight(self) -> None:
        c = QColorDialog.getColor(QColor("#fff176"), self, "Колір виділення")
        if c.isValid():
            self.edit.setTextBackgroundColor(c)

    def _clear_format(self) -> None:
        c = self.edit.textCursor()
        f = QTextCharFormat()
        f.setFont(self.edit.document().defaultFont())
        f.setForeground(QColor("black"))
        f.clearBackground()
        if c.hasSelection():
            c.setCharFormat(f)
        self.edit.setCurrentCharFormat(f)

    def _case(self, fn) -> None:
        c = self.edit.textCursor()
        if c.hasSelection():
            fmt = c.charFormat()
            c.insertText(fn(c.selectedText()), fmt)

    def _paste_plain(self) -> None:
        from PySide6.QtWidgets import QApplication
        self.edit.insertPlainText(QApplication.clipboard().text())

    # ---------- абзаци ----------
    def _align(self, a) -> None:
        self.edit.setAlignment(a)
        self._sync_toolbar()

    def _set_heading(self, idx: int) -> None:
        c = self.edit.textCursor()
        c.beginEditBlock()
        bf = QTextBlockFormat()
        bf.setHeadingLevel(idx)
        c.mergeBlockFormat(bf)
        cf = QTextCharFormat()
        cf.setFontPointSize(HEAD_SIZES.get(idx, 12))
        cf.setFontWeight(QFont.Weight.Bold if idx else QFont.Weight.Normal)
        c.select(QTextCursor.SelectionType.BlockUnderCursor)
        c.mergeCharFormat(cf)
        c.endEditBlock()
        self.edit.mergeCurrentCharFormat(cf)

    def _paragraph(self) -> None:
        c = self.edit.textCursor()
        d = ParagraphDialog(self, c.blockFormat(), self.edit.tabStopDistance())
        if d.exec():
            bf = c.blockFormat()
            tab = d.apply(bf)
            c.mergeBlockFormat(bf)
            self.edit.setTabStopDistance(tab)

    def _indent(self, d: int) -> None:
        c = self.edit.textCursor()
        bf = c.blockFormat()
        bf.setIndent(max(0, bf.indent() + d))
        c.setBlockFormat(bf)

    def _spacing(self) -> None:
        c = self.edit.textCursor()
        bf = c.blockFormat()
        cur = bf.lineHeight() / 100 if bf.lineHeightType() == QTextBlockFormat.LineHeightTypes.ProportionalHeight.value else 1.0
        d = SpacingDialog(self, cur or 1.0, bf.topMargin(), bf.bottomMargin())
        if d.exec():
            bf.setLineHeight(d.line_spacing() * 100, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            bf.setTopMargin(d.before.value())
            bf.setBottomMargin(d.after.value())
            c.setBlockFormat(bf)

    def _list_chosen(self, idx: int) -> None:
        if idx > 0:
            self._list(LIST_STYLES[idx - 1][1])
        self.cb_list.setCurrentIndex(0)

    def _list(self, style) -> None:
        c = self.edit.textCursor()
        if c.currentList() and c.currentList().format().style() == style:
            bf = c.blockFormat()
            bf.setObjectIndex(-1)
            bf.setIndent(0)
            c.setBlockFormat(bf)
        else:
            c.createList(style)

    def _sync_toolbar(self) -> None:
        c = self.edit.textCursor()
        cf = self.edit.currentCharFormat()
        self.a_bold.setChecked(cf.fontWeight() >= QFont.Weight.Bold)
        self.a_italic.setChecked(cf.fontItalic())
        self.a_under.setChecked(cf.fontUnderline())
        self.a_strike.setChecked(cf.fontStrikeOut())
        va = cf.verticalAlignment()
        self.a_sup.setChecked(va == QTextCharFormat.VerticalAlignment.AlignSuperScript)
        self.a_sub.setChecked(va == QTextCharFormat.VerticalAlignment.AlignSubScript)
        a = self.edit.alignment()
        self.a_left.setChecked(bool(a & Qt.AlignmentFlag.AlignLeft))
        self.a_center.setChecked(bool(a & Qt.AlignmentFlag.AlignHCenter))
        self.a_right.setChecked(bool(a & Qt.AlignmentFlag.AlignRight))
        self.a_just.setChecked(bool(a & Qt.AlignmentFlag.AlignJustify))
        for w in (self.cb_style, self.sp_size, self.cb_font):
            w.blockSignals(True)
        self.cb_style.setCurrentIndex(min(3, max(0, c.blockFormat().headingLevel())))
        self.sp_size.setValue(int(cf.fontPointSize() or 12))
        if cf.fontFamilies():
            self.cb_font.setCurrentFont(QFont(cf.fontFamilies()[0]))
        for w in (self.cb_style, self.sp_size, self.cb_font):
            w.blockSignals(False)
        self._sync_ruler()

    def _zoom(self, idx: int) -> None:
        k = (0.75, 1.0, 1.25, 1.5)[idx]
        self.edit.setFixedWidth(int(PAGE_W * k))
        self.edit.document().setPageSize(QSizeF(PAGE_W * k, PAGE_H * k))
        f = QFont(self.edit.document().defaultFont())
        self.edit.document().setDefaultFont(f)
        self.edit.setStyleSheet(f"QTextEdit {{ background: white; border: none; font-size: {12 * k:.1f}pt; }}")
        self.edit.set_page_setup(self.edit.setup)

    # ---------- таблиці ----------
    def _insert_table(self) -> None:
        d = TableDialog(self)
        if d.exec():
            self.insert_table(d.rows.value(), d.cols.value(), header=d.header.isChecked())

    def insert_table(self, rows: int, cols: int, data: list[list[str]] | None = None, header: bool = False) -> None:
        fmt = QTextTableFormat()
        fmt.setBorder(1)
        fmt.setCellPadding(4)
        fmt.setCellSpacing(0)
        fmt.setBorderStyle(QTextTableFormat.BorderStyle.BorderStyle_Solid)
        fmt.setBorderBrush(QColor("#444444"))
        c = self.edit.textCursor()
        t = c.insertTable(rows, cols, fmt)
        if data:
            for i, row in enumerate(data[:rows]):
                for j, val in enumerate(row[:cols]):
                    t.cellAt(i, j).firstCursorPosition().insertText(val)
        if header:
            bold = QTextCharFormat()
            bold.setFontWeight(QFont.Weight.Bold)
            for j in range(cols):
                cc = t.cellAt(0, j).firstCursorPosition()
                cc.select(QTextCursor.SelectionType.BlockUnderCursor)
                cc.mergeCharFormat(bold)
                t.cellAt(0, j).setFormat(self._cell_bg("#e3f1ec"))
        self.edit.setTextCursor(t.cellAt(0, 0).firstCursorPosition())

    @staticmethod
    def _cell_bg(color: str):
        from PySide6.QtGui import QTextTableCellFormat
        f = QTextTableCellFormat()
        f.setBackground(QColor(color))
        return f

    def _table(self):
        return self.edit.textCursor().currentTable()

    def _cell(self):
        t = self._table()
        if not t:
            self.statusBar().showMessage("Курсор не в таблиці")
            return None, None
        return t, t.cellAt(self.edit.textCursor())

    def _add_row(self) -> None:
        t, cell = self._cell()
        if t:
            t.insertRows(cell.row() + 1, 1)

    def _add_col(self) -> None:
        t, cell = self._cell()
        if t:
            t.insertColumns(cell.column() + 1, 1)

    def _del_row(self) -> None:
        t, cell = self._cell()
        if t:
            t.removeRows(cell.row(), 1)

    def _del_col(self) -> None:
        t, cell = self._cell()
        if t:
            t.removeColumns(cell.column(), 1)

    def _merge_cells(self) -> None:
        t = self._table()
        if t:
            t.mergeCells(self.edit.textCursor())

    def _split_cell(self) -> None:
        t, cell = self._cell()
        if t:
            t.splitCell(cell.row(), cell.column(), 1, 1)

    # ---------- стилі документа ----------
    def _refresh_styles(self) -> None:
        from .editor_styles import BUILTIN, saved_styles
        cur = self.cb_docstyle.currentText()
        self.cb_docstyle.blockSignals(True)
        self.cb_docstyle.clear()
        self.cb_docstyle.addItems(list(BUILTIN))
        self._saved_styles = saved_styles()
        self.cb_docstyle.addItems(list(self._saved_styles))
        if cur:
            self.cb_docstyle.setCurrentText(cur)
        self.cb_docstyle.blockSignals(False)

    def current_style(self):
        from .editor_styles import BUILTIN, DocStyle
        name = self.cb_docstyle.currentText()
        if name in BUILTIN:
            return BUILTIN[name]
        p = self._saved_styles.get(name)
        return DocStyle.load(p) if p else None

    def _apply_style(self, style=None) -> int:
        from .editor_styles import apply
        st = style if style is not None and not isinstance(style, bool) else self.current_style()
        if st is None:
            return 0
        n = apply(self.edit, st)
        self.statusBar().showMessage(f"Стиль «{st.name}» застосовано: абзаців {n}")
        return n

    def _save_style(self, path=None):
        from .editor_styles import STYLES_DIR, capture
        name, ok = QInputDialog.getText(self, "Зберегти стиль", "Назва стилю:", text="Мій стиль")
        if not ok or not name.strip():
            return None
        st = capture(self.edit, name.strip())
        if not path or isinstance(path, bool):
            safe = "".join(ch for ch in name if ch.isalnum() or ch in " _-").strip() or "style"
            p, _ = QFileDialog.getSaveFileName(self, "Зберегти стиль", str(STYLES_DIR / f"{safe}.json"), "Стиль InterText (*.json)")
            if not p:
                return None
            path = Path(p)
        st.save(path)
        self._refresh_styles()
        self.cb_docstyle.setCurrentText(st.name)
        self.statusBar().showMessage(f"Стиль збережено: {path}")
        return path

    def _load_style(self, path=None) -> int:
        from .editor_styles import DocStyle, STYLES_DIR
        if not path or isinstance(path, bool):
            p, _ = QFileDialog.getOpenFileName(self, "Завантажити стиль", str(STYLES_DIR), "Стиль InterText (*.json)")
            if not p:
                return 0
            path = Path(p)
        try:
            st = DocStyle.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Стиль", f"Не вдалося прочитати стиль:\n{e}")
            return 0
        if Path(path).parent != STYLES_DIR:          # копія в теку стилів, щоб був у списку
            st.save(STYLES_DIR / Path(path).name)
        self._refresh_styles()
        self.cb_docstyle.setCurrentText(st.name)
        return self._apply_style(st)

    # ---------- сторінка / ДСТУ ----------
    def _page_setup(self) -> None:
        d = PageSetupDialog(self, self.edit.setup)
        if d.exec():
            self.edit.set_page_setup(d.setup())
            self.edit.document().setModified(True)

    def _dstu(self) -> int:
        d = DstuDialog(self)
        if not d.exec():
            return 0
        return self.apply_dstu(d)

    def apply_dstu(self, opts: DstuDialog | None = None) -> int:
        opts = opts or DstuDialog(self)
        n = apply_dstu(self.edit, opts)
        if opts.margins.isChecked():
            self.edit.set_page_setup(DSTU)
        self.statusBar().showMessage(f"Автоформат за ДСТУ: абзаців {n}")
        return n

    def _first_line(self, mm: float) -> None:
        from .editor_page import MM
        c = self.edit.textCursor()
        bf = c.blockFormat()
        bf.setTextIndent(mm * MM)
        c.setBlockFormat(bf)

    def _table_props(self) -> None:
        t = self._table()
        if not t:
            self.statusBar().showMessage("Курсор не в таблиці")
            return
        d = TablePropsDialog(self, t)
        if d.exec():
            d.apply(self.edit.textCursor())

    def _image_props(self) -> None:
        c = self.edit.textCursor()
        f = c.charFormat()
        if not f.isImageFormat():
            c2 = QTextCursor(c)
            c2.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
            if c2.charFormat().isImageFormat():
                c, f = c2, c2.charFormat()
            else:
                self.statusBar().showMessage("Поставте курсор перед зображенням або двічі клацніть його")
                return
        imf = f.toImageFormat()
        l, r, _, _ = self.edit.setup.px()
        d = ImageDialog(self, int(imf.width()), int(imf.height()), PAGE_W - l - r)
        if d.exec():
            imf.setWidth(d.w.value())
            imf.setHeight(d.h.value())
            if not c.hasSelection():
                c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
            c.setCharFormat(imf)
            bf = c.blockFormat()
            bf.setAlignment(d.alignment())
            c.setBlockFormat(bf)

    # ---------- вставка ----------
    def _insert_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Зображення", "", "Зображення (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            self.insert_image(QImage(path))

    def insert_image(self, img: QImage, max_w: int | None = None) -> None:
        if img.isNull():
            return
        if max_w is None:
            l, r, _, _ = self.edit.setup.px()
            max_w = PAGE_W - l - r
        if img.width() > max_w:
            img = img.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)
        self._img_n += 1
        name = f"img{self._img_n}.png"
        self.edit.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), img)
        f = QTextImageFormat()
        f.setName(name)
        f.setWidth(img.width())
        f.setHeight(img.height())
        self.edit.textCursor().insertImage(f)

    def _insert_shape(self) -> None:
        from .shapes import ShapeDialog
        d = ShapeDialog(self)
        if d.exec():
            self.insert_image(d.image())

    def _insert_symbol(self) -> None:
        d = SymbolDialog(self)
        if d.exec() and d.chosen:
            self.edit.insertPlainText(d.chosen)

    def _insert_date(self) -> None:
        import datetime
        self.edit.insertPlainText(datetime.date.today().strftime("%d.%m.%Y"))

    def _page_break(self) -> None:
        c = self.edit.textCursor()
        bf = QTextBlockFormat()
        bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
        c.insertBlock(bf)
        c.setBlockFormat(QTextBlockFormat())

    def _insert_formula(self) -> None:
        c = self.edit.textCursor()
        current = c.charFormat().toolTip() or ""
        d = FormulaDialog(self, current)
        if d.exec() and d.latex():
            self.insert_formula(d.latex())

    def insert_formula(self, latex: str) -> None:
        c = self.edit.textCursor()
        if c.charFormat().toolTip() and not c.hasSelection():      # замінити наявну формулу
            c.select(QTextCursor.SelectionType.WordUnderCursor)
        f = QTextCharFormat()
        f.setFontItalic(True)
        f.setToolTip(latex)
        f.setFontFamilies(["Cambria Math", "Times New Roman"])
        c.insertText(latex_to_unicode(latex), f)
        c.insertText(" ", QTextCharFormat())
        self.edit.setTextCursor(c)

    # ---------- сторінки, зміст, шаблони ----------
    def _title(self) -> str:
        return self.path.stem if self.path else "документ"

    def _headers(self) -> None:
        d = HeaderFooterDialog(self, self.hf)
        if d.exec():
            self.hf = d.result_hf()
            self.statusBar().showMessage("Колонтитули видно в перегляді друку, PDF і DOCX")

    def _toc(self) -> None:
        if not insert_toc(self.edit):
            QMessageBox.information(self, "Зміст", "Немає заголовків. Позначте розділи стилем «Заголовок 1–3» (вкладка «Текст»).")

    def _template(self, name: str) -> None:
        if self.edit.document().isModified() and self.edit.toPlainText().strip() and QMessageBox.question(
                self, "Шаблон", "Замінити поточний текст шаблоном «%s»?" % name) != QMessageBox.StandardButton.Yes:
            return
        self.set_html(TEMPLATES[name])
        self.path = None
        if name in ("Наказ", "Протокол засідання", "Службовий лист"):
            self.hf = HeaderFooter(header="{стор}")
        self.statusBar().showMessage("Заповніть поля в [квадратних дужках]")

    # ---------- файли ----------
    def _new(self) -> None:
        if self.edit.document().isModified() and QMessageBox.question(
                self, "Новий документ", "Є незбережені зміни. Створити новий документ?") != QMessageBox.StandardButton.Yes:
            return
        self.edit.clear()
        self.path = None
        self.edit.document().setModified(False)

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Відкрити документ", "",
                                              "Документи (*.docx *.html *.htm *.txt);;Усі файли (*)")
        if path:
            self.load(Path(path))

    def load(self, path: Path) -> None:
        ext = path.suffix.lower()
        try:
            if ext == ".docx":
                from ..export.html_docx import docx_to_html
                html, images = docx_to_html(path, with_images=True)
                margins = images.pop("__margins_mm__", None)
                for name, data in images.items():
                    img = QImage.fromData(data)
                    if not img.isNull():
                        self.edit.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), img)
                if margins:
                    self.edit.setup = PageSetup(*(round(float(v), 1) for v in margins))
                self.set_html(html)
                adaptation_notice(self, "DOCX")
            elif ext in (".html", ".htm"):
                self.set_html(path.read_text(encoding="utf-8", errors="replace"))
            else:
                self.edit.setPlainText(path.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            QMessageBox.critical(self, "Відкрити", f"Не вдалося відкрити {path.name}:\n{e}")
            return
        self.path = path
        self.setWindowTitle(f"{path.name} — {INTERTEXT} · {APP_NAME}")
        self.statusBar().showMessage(f"Відкрито: {path}")

    def save(self) -> None:
        if self.path and self.path.suffix.lower() in (".docx", ".html", ".htm", ".txt"):
            self.save_to(self.path)
        else:
            self.save_as("docx")

    def save_as(self, fmt: str) -> None:
        filters = {"docx": "Word (*.docx)", "pdf": "PDF (*.pdf)", "html": "HTML (*.html)", "txt": "Текст (*.txt)"}
        start = str(self.path.with_suffix("." + fmt)) if self.path else f"документ.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, "Зберегти як", start, filters[fmt])
        if path:
            self.save_to(Path(path))

    def _images_png(self) -> dict[str, bytes]:
        """Ресурси-зображення документа як PNG (для DOCX і HTML)."""
        from PySide6.QtCore import QBuffer, QIODevice
        out = {}
        block = self.edit.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fr = it.fragment()
                if fr.isValid() and fr.charFormat().isImageFormat():
                    name = fr.charFormat().toImageFormat().name()
                    img = self.edit.resource_image(name)
                    if img is not None and name not in out:
                        buf = QBuffer()
                        buf.open(QIODevice.OpenModeFlag.WriteOnly)
                        img.save(buf, "PNG")
                        out[name] = bytes(buf.data())
                it += 1
            block = block.next()
        return out

    def save_to(self, path: Path) -> Path | None:
        ext = path.suffix.lower()
        try:
            if ext == ".docx":
                from ..export.html_docx import html_to_docx
                path.parent.mkdir(parents=True, exist_ok=True)
                st = self.edit.setup
                dx = html_to_docx(self.html(), self._images_png(), (st.left, st.right, st.top, st.bottom))
                docx_add_hf(dx, self.hf, self._title())
                dx.save(str(path))
            elif ext == ".pdf":
                from PySide6.QtPrintSupport import QPrinter
                pr = QPrinter(QPrinter.PrinterMode.HighResolution)
                pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                pr.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
                pr.setOutputFileName(str(path))
                render_pages(self.edit.document(), pr, self.edit.setup, self.hf, self._title())
            elif ext in (".html", ".htm"):
                html = self.html()
                for name, data in self._images_png().items():
                    html = html.replace(f'src="{name}"', f'src="data:image/png;base64,{base64.b64encode(data).decode()}"')
                path.write_text(html, encoding="utf-8")
            else:
                path.write_text(self.edit.toPlainText(), encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Зберегти", f"Не вдалося зберегти:\n{e}")
            return None
        if ext != ".pdf":
            self.path = path
            self.edit.document().setModified(False)
        self.statusBar().showMessage(f"Збережено: {path}")
        return path

    def _print(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        pr = QPrinter(QPrinter.PrinterMode.HighResolution)
        pr.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        if QPrintDialog(pr, self).exec():
            render_pages(self.edit.document(), pr, self.edit.setup, self.hf, self._title())

    def _preview(self) -> None:
        from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
        pr = QPrinter(QPrinter.PrinterMode.HighResolution)
        pr.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        d = QPrintPreviewDialog(pr, self)
        d.paintRequested.connect(lambda p: render_pages(self.edit.document(), p, self.edit.setup, self.hf, self._title()))
        d.exec()

    def closeEvent(self, e) -> None:
        if self.edit.document().isModified() and QMessageBox.question(
                self, "Закрити", "Є незбережені зміни. Закрити редактор?") != QMessageBox.StandardButton.Yes:
            e.ignore()
            return
        e.accept()
