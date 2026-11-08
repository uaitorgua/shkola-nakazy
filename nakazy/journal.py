"""Реєстраційний журнал наказів (форма дод. 4 до Інструкції МОН № 676) у DOCX.

Оформлення за дод. 1: Times New Roman, поля 30/10/20/20 мм. Таблиця: шапка повторюється на
кожній сторінці, рядки не розриваються між сторінками.
"""
from __future__ import annotations

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt

from .db import KIND_BY_CODE, Database, format_date

COLUMNS = [  # (назва графи за дод. 4, ширина мм)
    ("Реєстраційний індекс (номер) наказу", 25),
    ("Дата наказу", 22),
    ("Заголовок наказу", 95),
    ("Прізвище, ініціали працівника, на якого покладено контроль виконання", 45),
    ("Прізвище, ініціали відповідальної особи (осіб)", 45),
    ("Примітки", 25),
]


def _repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader"); el.set(qn("w:val"), "true"); tr_pr.append(el)


def _no_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:cantSplit"); el.set(qn("w:val"), "true"); tr_pr.append(el)


def export_journal_docx(db: Database, kind: str, year: int, path: str):
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"; st.font.size = Pt(12)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Mm(297), Mm(210)
    sec.left_margin, sec.right_margin = Mm(30), Mm(10)
    sec.top_margin = sec.bottom_margin = Mm(20)

    school = db.get_setting("school")
    if school:
        p = doc.add_paragraph(school); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("РЕЄСТРАЦІЙНИЙ ЖУРНАЛ НАКАЗІВ").bold = True
    p = doc.add_paragraph(f"{KIND_BY_CODE[kind].journal}, {year} рік"); p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    t = doc.add_table(rows=2, cols=len(COLUMNS))
    t.style = "Table Grid"
    for i, (name, w) in enumerate(COLUMNS):
        for r in (0, 1):
            c = t.rows[r].cells[i]; c.width = Mm(w)
            c.text = name if r == 0 else str(i + 1)
            par = c.paragraphs[0]; par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in par.runs:
                run.font.size = Pt(10); run.bold = r == 0
    _repeat_header(t.rows[0]); _repeat_header(t.rows[1])  # шапка і номери граф на кожній сторінці

    for o in db.journal(kind, year):
        note = o["notes"]
        if o["status"] == "cancelled" and "Скасовано" not in note:
            note = "Скасовано. " + note
        vals = [o["reg_index"], format_date(o["date"]), o["title"], o["controller"], o["responsible"], note]
        row = t.add_row(); _no_split(row)
        for i, v in enumerate(vals):
            row.cells[i].width = Mm(COLUMNS[i][1]); row.cells[i].text = v or ""
            for run in row.cells[i].paragraphs[0].runs:
                run.font.size = Pt(11)
    doc.save(path)
    return path
