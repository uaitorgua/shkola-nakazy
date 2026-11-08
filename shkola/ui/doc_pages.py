"""InterText: колонтитули з полями ({стор}, {усього}, {дата}, {назва}), друк/PDF посторінково з колонтитулами,
зміст за заголовками, шаблони шкільних документів."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QFont, QPainter, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QSpinBox)

from .editor_page import MM, PageSetup, apply_page_setup

PAGE_W, PAGE_H = 794, 1123          # A4 при 96 dpi (як у editor_window)
FIELDS_HINT = "Поля: {стор} — номер сторінки, {усього} — кількість сторінок, {дата}, {назва} — назва файлу"
NUMBER_PRESETS = {"Без номера": ("", ""), "Номер унизу по центру": ("", "{стор}"),
                  "Номер унизу праворуч": ("", "\t\t{стор}"), "Номер угорі по центру (ДСТУ)": ("{стор}", ""),
                  "«Сторінка N з M» унизу": ("", "Сторінка {стор} з {усього}")}


@dataclass
class HeaderFooter:
    header: str = ""
    footer: str = ""
    skip_first: bool = True     # на першій сторінці колонтитулів немає (за ДСТУ номер з другої)
    size_pt: int = 10

    def active(self) -> bool:
        return bool(self.header.strip() or self.footer.strip())

    def text(self, which: str, page: int, pages: int, title: str = "") -> str:
        s = self.header if which == "header" else self.footer
        return (s.replace("{стор}", str(page)).replace("{усього}", str(pages))
                .replace("{дата}", _dt.date.today().strftime("%d.%m.%Y")).replace("{назва}", title))


class HeaderFooterDialog(QDialog):
    def __init__(self, parent, hf: HeaderFooter) -> None:
        super().__init__(parent)
        self.setWindowTitle("Колонтитули й нумерація")
        f = QFormLayout(self)
        self.preset = QComboBox()
        self.preset.addItem("Свій варіант")
        self.preset.addItems(NUMBER_PRESETS)
        self.preset.activated.connect(self._preset)
        self.ed_h = QLineEdit(hf.header)
        self.ed_f = QLineEdit(hf.footer)
        for e in (self.ed_h, self.ed_f):
            e.setPlaceholderText("Ліва частина\tцентр\tправа — розділяйте табуляцією (\\t)")
        self.cb_first = QCheckBox("Не показувати на першій сторінці")
        self.cb_first.setChecked(hf.skip_first)
        self.sp = QSpinBox()
        self.sp.setRange(7, 14)
        self.sp.setValue(hf.size_pt)
        self.sp.setSuffix(" пт")
        f.addRow("Швидкий вибір", self.preset)
        f.addRow("Верхній", self.ed_h)
        f.addRow("Нижній", self.ed_f)
        f.addRow("", self.cb_first)
        f.addRow("Розмір", self.sp)
        hint = QLabel(FIELDS_HINT + ". Частини «ліво\\tцентр\\tправо» розділяються знаком \\t.")
        hint.setWordWrap(True)
        f.addRow(hint)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _preset(self, i: int) -> None:
        if i > 0:
            h, ft = NUMBER_PRESETS[self.preset.itemText(i)]
            self.ed_h.setText(h.replace("\t", "\\t"))
            self.ed_f.setText(ft.replace("\t", "\\t"))

    def result_hf(self) -> HeaderFooter:
        u = lambda s: s.replace("\\t", "\t")
        return HeaderFooter(u(self.ed_h.text()), u(self.ed_f.text()), self.cb_first.isChecked(), self.sp.value())


def _draw_band(p: QPainter, text: str, rect: QRectF, size_pt: int) -> None:
    if not text:
        return
    f = QFont("Times New Roman")
    f.setPixelSize(round(size_pt * 96 / 72))
    p.setFont(f)
    parts = text.split("\t")
    if len(parts) == 1:
        parts = ["", parts[0], ""]          # один фрагмент — по центру
    parts = (parts + ["", ""])[:3]
    for s, al in zip(parts, (Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignRight)):
        if s:
            p.drawText(rect, int(al | Qt.AlignmentFlag.AlignVCenter), s)


def render_pages(doc, printer, setup: PageSetup, hf: HeaderFooter | None, title: str = "") -> int:
    """Друкує документ на принтер/PDF сторінками A4 із колонтитулами. Повертає кількість сторінок."""
    d = doc.clone()
    apply_page_setup(d, setup)
    d.setPageSize(QSizeF(PAGE_W, PAGE_H))
    printer.setFullPage(True)
    pages = d.pageCount()
    p = QPainter(printer)
    k = printer.width() / PAGE_W
    l, r, t, b = setup.px()
    for i in range(pages):
        if i:
            printer.newPage()
        p.save()
        p.scale(k, k)
        p.save()
        p.translate(0, -i * PAGE_H)
        d.drawContents(p, QRectF(0, i * PAGE_H, PAGE_W, PAGE_H))
        p.restore()
        if hf and hf.active() and not (hf.skip_first and i == 0):
            band = 8 * MM
            _draw_band(p, hf.text("header", i + 1, pages, title), QRectF(l, max(2 * MM, t - band - 2 * MM), PAGE_W - l - r, band), hf.size_pt)
            _draw_band(p, hf.text("footer", i + 1, pages, title), QRectF(l, PAGE_H - b + 2 * MM, PAGE_W - l - r, band), hf.size_pt)
        p.restore()
    p.end()
    return pages


def insert_toc(edit) -> int:
    """Зміст за заголовками 1–3 з номерами сторінок у позицію курсора. Повертає кількість пунктів."""
    doc = edit.document()
    lay = doc.documentLayout()
    ph = doc.pageSize().height() or PAGE_H
    items = []
    b = doc.begin()
    while b.isValid():
        lvl = b.blockFormat().headingLevel()
        if 1 <= lvl <= 3 and b.text().strip():
            items.append((lvl, b.text().strip(), int(lay.blockBoundingRect(b).top() // ph) + 1))
        b = b.next()
    if not items:
        return 0
    l, r, _t, _b = edit.setup.px()
    width = doc.pageSize().width() - l - r
    c = edit.textCursor()
    c.beginEditBlock()
    tf = QTextBlockFormat()
    tf.setHeadingLevel(0)
    tf.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    hcf = QTextCharFormat()
    hcf.setFontWeight(QFont.Weight.Bold)
    hcf.setFontPointSize(14)
    c.insertBlock(tf, hcf)
    c.insertText("ЗМІСТ")
    for lvl, text, page in items:
        bf = QTextBlockFormat()
        bf.setHeadingLevel(0)
        bf.setLeftMargin((lvl - 1) * 8 * MM)
        bf.setTabPositions([QTextOption.Tab(width - (lvl - 1) * 8 * MM - 2, QTextOption.TabType.RightTab)])
        cf = QTextCharFormat()
        cf.setFontPointSize(12)
        cf.setFontWeight(QFont.Weight.Bold if lvl == 1 else QFont.Weight.Normal)
        c.insertBlock(bf, cf)
        c.insertText(f"{text}\t{page}")
    c.insertBlock(QTextBlockFormat(), QTextCharFormat())
    c.endEditBlock()
    return len(items)


# ---------- шаблони (поля для заповнення в [квадратних дужках]) ----------
_P = '<p style="text-align:{a}; text-indent:{i}mm; margin:0 0 6px 0; font-family:Times New Roman; font-size:14pt;">{t}</p>'


def _p(t, a="justify", i=10):
    return _P.format(a=a, i=i, t=t)


def _head(t):
    return f'<h1 style="text-align:center; font-family:Times New Roman; font-size:14pt; font-weight:700;">{t}</h1>'


TEMPLATES = {
    "Наказ": (_p("[НАЗВА ЗАКЛАДУ ОСВІТИ]", "center", 0) + _p("<b>НАКАЗ</b>", "center", 0)
              + _p("[дд.мм.рррр]\t[місто]\t№ [номер]", "left", 0) + _p("<b>Про [короткий зміст]</b>", "left", 0)
              + _p("Відповідно до [підстава] та з метою [мета]")
              + _p("НАКАЗУЮ:", "left", 0) + _p("1. [Перше розпорядження].") + _p("2. [Друге розпорядження].")
              + _p("3. Контроль за виконанням наказу покласти на [посада, ПІБ].")
              + _p("<br/>Директор\t\t[Власне ім'я ПРІЗВИЩЕ]", "left", 0)
              + _p("З наказом ознайомлені:", "left", 0)),
    "Протокол засідання": (_p("[НАЗВА ЗАКЛАДУ ОСВІТИ]", "center", 0) + _p("<b>ПРОТОКОЛ</b>", "center", 0)
                           + _p("засідання [педагогічної ради / методичного об'єднання]", "center", 0)
                           + _p("[дд.мм.рррр]\t№ [номер]", "left", 0)
                           + _p("Голова — [ПІБ]<br/>Секретар — [ПІБ]<br/>Присутні: [кількість] осіб (список додається)", "left", 0)
                           + _p("<b>ПОРЯДОК ДЕННИЙ:</b>", "left", 0) + _p("1. [Питання].") + _p("2. [Питання].")
                           + _p("<b>1. СЛУХАЛИ:</b> [ПІБ] — [зміст виступу].", "left", 0)
                           + _p("<b>ВИСТУПИЛИ:</b> [ПІБ] — [зміст].", "left", 0)
                           + _p("<b>УХВАЛИЛИ:</b> [рішення].", "left", 0)
                           + _p("<br/>Голова\t\t[Власне ім'я ПРІЗВИЩЕ]<br/>Секретар\t\t[Власне ім'я ПРІЗВИЩЕ]", "left", 0)),
    "Службовий лист": (_p("[НАЗВА ЗАКЛАДУ ОСВІТИ]<br/>[адреса, телефон, e-mail, код ЄДРПОУ]", "center", 0)
                       + _p("[дд.мм.рррр] № [вихідний номер]", "left", 0)
                       + _p("[Посада й назва установи адресата]<br/>[Власне ім'я ПРІЗВИЩЕ]", "right", 0)
                       + _p("<b>Про [короткий зміст]</b>", "left", 0)
                       + _p("[Текст листа: мета звернення, обґрунтування, прохання або пропозиція.]")
                       + _p("<br/>Директор\t\t[Власне ім'я ПРІЗВИЩЕ]", "left", 0)
                       + _p("<span style='font-size:10pt'>[Прізвище виконавця] [телефон]</span>", "left", 0)),
    "План-конспект уроку": (_head("План-конспект уроку") + _p("<b>Предмет:</b> [предмет]   <b>Клас:</b> [клас]   <b>Дата:</b> [дата]", "left", 0)
                            + _p("<b>Тема:</b> [тема уроку]", "left", 0) + _p("<b>Мета:</b> [навчальна, розвивальна, виховна]", "left", 0)
                            + _p("<b>Очікувані результати:</b> [що учні знатимуть і вмітимуть]", "left", 0)
                            + _p("<b>Тип уроку:</b> [тип]   <b>Обладнання:</b> [обладнання]", "left", 0)
                            + _head("Хід уроку")
                            + _p("<b>I. Організаційний момент</b> ([хв])", "left", 0) + _p("<b>II. Актуалізація знань</b> ([хв])", "left", 0)
                            + _p("<b>III. Вивчення нового матеріалу</b> ([хв])", "left", 0) + _p("<b>IV. Закріплення</b> ([хв])", "left", 0)
                            + _p("<b>V. Підсумок і рефлексія</b> ([хв])", "left", 0) + _p("<b>VI. Домашнє завдання:</b> [завдання]", "left", 0)),
    "Оголошення": (_p("<b>ОГОЛОШЕННЯ</b>", "center", 0) + _p("[Дата й час] у [місце] відбудеться [подія].")
                   + _p("Запрошуються: [хто].") + _p("Контактна особа: [ПІБ, телефон].") + _p("<br/>[Адміністрація закладу]", "right", 0)),
}


def docx_add_hf(d, hf: HeaderFooter | None, title: str = "") -> None:
    """Колонтитули в DOCX: {стор}/{усього} → поля PAGE/NUMPAGES, частини через табуляцію."""
    if not hf or not hf.active():
        return
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt
    import re
    sec = d.sections[0]
    sec.different_first_page_header_footer = hf.skip_first

    def field(par, code):
        run = par.add_run()
        for tag, attr in (("w:fldChar", "begin"), ("w:instrText", None), ("w:fldChar", "end")):
            el = OxmlElement(tag)
            if attr:
                el.set(qn("w:fldCharType"), attr)
            else:
                el.set(qn("xml:space"), "preserve")
                el.text = f" {code} "
            run._r.append(el)
        run.font.size = Pt(hf.size_pt)

    for text, part in ((hf.header, sec.header), (hf.footer, sec.footer)):
        if not text.strip():
            continue
        part.is_linked_to_previous = False
        par = part.paragraphs[0]
        parts = text.split("\t")
        if len(parts) == 1:
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        txt = text.replace("{дата}", _dt.date.today().strftime("%d.%m.%Y")).replace("{назва}", title)
        for tok in re.split(r"(\{стор\}|\{усього\})", txt):
            if tok == "{стор}":
                field(par, "PAGE")
            elif tok == "{усього}":
                field(par, "NUMPAGES")
            elif tok:
                r = par.add_run(tok)
                r.font.size = Pt(hf.size_pt)
