"""Експорт наказу в DOCX і PDF за дод. 1 до Інструкції МОН № 676.

- A4, поля 30/10/20/20 мм, Times New Roman 12–14 (дод. 1 пп. 1–2);
- бланк закладу лише на першій сторінці (зображення, готовий DOCX або текстовий з полів);
- «НАКАЗ» великими (дод. 1 п. 3); дата, місце видання, номер; заголовок «Про…» без відступу;
- підпис: посада ліворуч, «Власне ім'я ПРІЗВИЩЕ» з відступом 125 мм на рівні останнього рядка посади
  (дод. 1 п. 4 № 676; ДСТУ 4163:2020 пп. 5.22, 7.7);
- відмітка про ознайомлення (за налаштуванням): «З наказом ознайомлені:», підпис, ім'я, дата (ДСТУ п. 5.28);
- перша сторінка без номера, далі номери вгорі по центру (дод. 1 п. 7);
- додатки: кожен з нової сторінки, гриф «Додаток N до наказу … від … № …» праворуч
  (група з наказом, р. VI п. 4); відступ грифа 100 мм (ДСТУ п. 7.7) або інший з налаштувань;
  документ, затверджений наказом, – гриф «ЗАТВЕРДЖЕНО / Наказ … / дата № …» (ДСТУ п. 5.16);
- таблиці 12–14 пт, як і текст (дод. 1 п. 1 № 676);
- вкладені файли-додатки: у PDF дописуються після наказу, у DOCX – перелік.
"""
from __future__ import annotations

import copy
import io
import os
import shutil
import subprocess
import tempfile

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt

from shkola.export.html_docx import html_to_docx

from .db import Database, format_date

MARGINS = (30, 10, 20, 20)  # ліве, праве, верхнє, нижнє, мм (дод. 1 п. 2)
TEXT_W = 210 - MARGINS[0] - MARGINS[1]
GRIF_INDENT = 100  # мм від лівого поля (ДСТУ 4163:2020 п. 7.7)
SIGN_INDENT = 125  # розшифрування підпису (ДСТУ п. 7.7)


def dstu_signature(name: str) -> str:
    """«Олена Петренко», «Петренко Олена Іванівна», «О. Петренко» → «Олена ПЕТРЕНКО» / «О. ПЕТРЕНКО» (ДСТУ п. 5.22)."""
    parts = [p for p in name.replace(",", " ").split() if p]
    if not parts:
        return ""
    if len(parts) >= 3 and not parts[0].endswith("."):  # Прізвище Ім'я По батькові
        return f"{parts[1]} {parts[0].upper()}"
    return " ".join(parts[:-1] + [parts[-1].upper()])


def _html(fragment: str) -> str:
    """Конвертер InterText читає вміст лише всередині <body>; шаблони дають фрагмент."""
    return fragment if "<body" in (fragment or "").lower() else f"<html><body>{fragment or ''}</body></html>"


def _font(run, size=None, bold=None):
    run.font.name = "Times New Roman"
    run._r.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Times New Roman")
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold


def _para(doc, text="", size=14, bold=False, align=None, before=0, after=0, indent_mm=None):
    p = doc.add_paragraph()
    if text:
        _font(p.add_run(text), size, bold)
    pf = p.paragraph_format
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    pf.first_line_indent = Mm(0)
    if align is not None:
        p.alignment = align
    if indent_mm is not None:
        pf.left_indent = Mm(indent_mm)
    return p


def _move_to_start(doc, elements):
    body = doc.element.body
    for i, el in enumerate(elements):
        body.remove(el)
        body.insert(i, el)


def _page_field(par, size):
    run = par.add_run()
    for tag, attr in (("w:fldChar", "begin"), ("w:instrText", None), ("w:fldChar", "end")):
        el = OxmlElement(tag)
        if attr:
            el.set(qn("w:fldCharType"), attr)
        else:
            el.set(qn("xml:space"), "preserve"); el.text = " PAGE "
        run._r.append(el)
    _font(run, size)


def _blank_elements(doc, blank: dict | None, school: str, size: int) -> list:
    """Додає елементи бланка в кінець документа й повертає їх (потім переносяться на початок)."""
    body = doc.element.body
    before = len(body)
    f = (blank or {}).get("fields", {})
    mode = (blank or {}).get("mode", "text")
    if mode == "image" and blank.get("data"):
        w = float(f.get("width_mm") or TEXT_W)
        p = _para(doc, align=WD_ALIGN_PARAGRAPH.CENTER)
        p.add_run().add_picture(io.BytesIO(blank["data"]), width=Mm(min(w, TEXT_W)))
    elif mode == "docx" and blank.get("data"):
        src = Document(io.BytesIO(blank["data"]))
        for el in list(src.element.body):
            if el.tag == qn("w:sectPr"):
                continue
            new = copy.deepcopy(el)
            for blip in new.iter(qn("a:blip")):  # зображення (герб) переносимо разом з бланком
                rid = blip.get(qn("r:embed"))
                if rid and rid in src.part.related_parts:
                    blip.set(qn("r:embed"), doc.part.relate_to(src.part.related_parts[rid], RT.IMAGE))
            body.insert(len(body) - 1, new)  # перед sectPr
    else:
        for key, sz, bold in (("owner", size - 2, False), ("school", size, True), ("address", size - 3, False)):
            text = f.get(key) or (school if key == "school" else "")
            if text:
                _para(doc, text, sz, bold, WD_ALIGN_PARAGRAPH.CENTER)
    if not f.get("has_nakaz"):
        _para(doc, "НАКАЗ", size, True, WD_ALIGN_PARAGRAPH.CENTER, before=12)
    els = list(body)[before - 1:len(body) - 1] if body[-1].tag == qn("w:sectPr") else list(body)[before:]
    return [e for e in els if e.tag != qn("w:sectPr")]


def build_docx(db: Database, order_id: int) -> Document:
    o = db.get(order_id)
    size = int(db.get_setting("font_size", "14") or 14)
    school = db.get_setting("school")
    city = db.get_setting("city")
    # 1) тіло наказу з редактора
    doc = html_to_docx(_html(o["body_html"]), None, MARGINS)
    for p in doc.paragraphs:
        p.paragraph_format.first_line_indent = Mm(0) if p.text.strip().startswith("НАКАЗУЮ") else \
            p.paragraph_format.first_line_indent
        for r in p.runs:
            if not r.font.size or r.font.size == Pt(12):
                _font(r, size)
    st = doc.styles["Normal"]; st.font.size = Pt(size)
    for p in doc.paragraphs:  # дод. 1 п. 2: інтервал 1–1,5; між абзацами без великих проміжків
        pf = p.paragraph_format
        pf.space_before, pf.space_after, pf.line_spacing = Pt(0), Pt(0), 1.15
        if p.text.strip().startswith("НАКАЗУЮ"):
            pf.space_before = pf.space_after = Pt(6)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.left_margin, sec.right_margin, sec.top_margin, sec.bottom_margin = (Mm(v) for v in MARGINS)
    sec.header_distance = Mm(10)

    # 2) шапка: бланк, дата / місце / номер, заголовок
    head = _blank_elements(doc, db.default_blank(), school, size)
    p = _para(doc, size=size, before=12)
    tabs = p.paragraph_format.tab_stops
    tabs.add_tab_stop(Mm(TEXT_W / 2), WD_TAB_ALIGNMENT.CENTER)
    tabs.add_tab_stop(Mm(TEXT_W), WD_TAB_ALIGNMENT.RIGHT)
    date = format_date(o["date"]) or "____________"
    number = o["reg_index"] or "______"
    _font(p.add_run(f"{date}\t{('м. ' + city) if city and not city.startswith(('м.', 'с.', 'смт')) else city}"
                    f"\t№ {number}"), size)
    t = _para(doc, o["title"], size, True, before=12, after=12)
    t.paragraph_format.keep_with_next = True
    _move_to_start(doc, head + [p._p, t._p])

    # 3) підпис (дод. 1 п. 4) і, за налаштуванням, ознайомлення
    position = ("В. о. директора" if o["signer_acting"] else db.get_setting("head_position", "Директор"))
    s = _para(doc, size=size, before=24)
    s.paragraph_format.tab_stops.add_tab_stop(Mm(SIGN_INDENT), WD_TAB_ALIGNMENT.LEFT)
    s.paragraph_format.keep_together = True
    _font(s.add_run(f"{position}\t{o['signer']}"), size)
    if db.get_setting("acquaint") == "1":
        # ДСТУ 4163:2020 п. 5.28: підпис, власне ім'я ПРІЗВИЩЕ, дата (власноручно), нижче реквізиту «Підпис»
        s.paragraph_format.keep_with_next = True
        names = [dstu_signature(x) for x in (o["responsible"] or "").split(",") if x.strip()]
        _para(doc, "З наказом ознайомлені:", size, before=18).paragraph_format.keep_with_next = True
        for name in names or ["", "", ""]:
            q = _para(doc, size=size, before=8)
            tabs = q.paragraph_format.tab_stops
            tabs.add_tab_stop(Mm(45), WD_TAB_ALIGNMENT.LEFT)
            tabs.add_tab_stop(Mm(TEXT_W), WD_TAB_ALIGNMENT.RIGHT)
            _font(q.add_run(f"____________\t{name or '______________________'}\t____________"), size)

    # 4) номери сторінок з другої (дод. 1 п. 7)
    sec.different_first_page_header_footer = True
    hp = sec.header.paragraphs[0]; hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _page_field(hp, 12)

    # 5) додатки
    files = []
    for a in db.attachments(order_id):
        if a["mode"] == "file":
            files.append(a); continue
        br = _para(doc); br.add_run().add_break(WD_BREAK.PAGE)
        grif = float(db.get_setting("grif_indent", str(GRIF_INDENT)) or GRIF_INDENT)
        lines = ([f"Додаток {a['n']}", "до наказу", f"від {date} № {number}"] if not a["approved"] else
                 ["ЗАТВЕРДЖЕНО", f"Наказ {db.get_setting('head_genitive', 'директора')}", f"{date} № {number}"])
        for line in lines:
            _para(doc, line, size, indent_mm=grif)
        _para(doc, a["title"], size, True, WD_ALIGN_PARAGRAPH.CENTER, before=18, after=12)
        if (a["body_html"] or "").strip():
            sub = html_to_docx(_html(a["body_html"]))
            for el in list(sub.element.body):
                if el.tag != qn("w:sectPr"):
                    doc.element.body.insert(len(doc.element.body) - 1, copy.deepcopy(el))
    if files:
        _para(doc, "Додатки окремими файлами: " + "; ".join(
            f"додаток {a['n']} «{a['title']}» ({a['filename']})" for a in files), size - 2, before=18)
    format_tables(doc, size)
    return doc


def _tr_flag(row, tag):
    pr = row._tr.get_or_add_trPr(); el = OxmlElement(tag); el.set(qn("w:val"), "true"); pr.append(el)


def format_tables(doc, size: int):
    """Таблиці: на всю ширину тексту, шапка жирна по центру й повторюється на кожній сторінці,
    рядок не розривається між сторінками, кегль на 2 менше за основний (не менше 10)."""
    tsize = max(12, size - 2)  # не менше 12 пт: дод. 1 п. 1 № 676
    for t in doc.tables:
        t.style = "Table Grid"
        t.autofit = False
        ncols = len(t.columns) or 1
        for ri, row in enumerate(t.rows):
            _tr_flag(row, "w:cantSplit")
            if ri == 0:
                _tr_flag(row, "w:tblHeader")
            for cell in row.cells:
                cell.width = Mm(TEXT_W / ncols)
                for par in cell.paragraphs:
                    pf = par.paragraph_format
                    pf.space_before = pf.space_after = Pt(0); pf.first_line_indent = Mm(0)
                    if ri == 0:
                        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for r in par.runs:
                        _font(r, tsize, True if ri == 0 else None)


def export_docx(db: Database, order_id: int, path: str) -> str:
    build_docx(db, order_id).save(path)
    return path


def _docx_to_pdf(docx_path: str, pdf_path: str):
    """Word (якщо встановлено) або LibreOffice; без інтернету."""
    try:
        import win32com.client  # type: ignore
        word = win32com.client.DispatchEx("Word.Application"); word.Visible = False
        try:
            d = word.Documents.Open(os.path.abspath(docx_path), ReadOnly=True)
            d.ExportAsFixedFormat(os.path.abspath(pdf_path), 17); d.Close(False)
            return
        finally:
            word.Quit()
    except Exception:
        pass
    soffice = shutil.which("soffice") or next((p for p in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe") if os.path.exists(p)), None)
    if not soffice:
        raise RuntimeError("Для PDF потрібен Microsoft Word або LibreOffice. Збережіть наказ у DOCX.")
    out = tempfile.mkdtemp()
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", out, docx_path],
                   check=True, capture_output=True, timeout=180)
    shutil.move(os.path.join(out, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf"), pdf_path)


def export_pdf(db: Database, order_id: int, path: str) -> str:
    from pypdf import PdfReader, PdfWriter
    tmp = tempfile.mkdtemp()
    dx = os.path.join(tmp, "order.docx")
    export_docx(db, order_id, dx)
    base = os.path.join(tmp, "order.pdf")
    _docx_to_pdf(dx, base)
    w = PdfWriter(); w.append(PdfReader(base))
    for a in db.attachments(order_id):
        if a["mode"] == "file" and (a["filename"] or "").lower().endswith(".pdf") and a["data"]:
            w.append(PdfReader(io.BytesIO(a["data"])))
    with open(path, "wb") as fh:
        w.write(fh)
    return path
