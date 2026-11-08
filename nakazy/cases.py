"""Номенклатура справ і строки зберігання наказів; формування справи за видом і роком.

Норми:
- № 676 р. V: номенклатура справ – обов'язковий перелік справ зі строками зберігання; затверджується
  не пізніше 20 грудня, діє з 1 січня (п. 12);
- № 676 р. VI п. 3: накази групуються в різні справи за видами й строками зберігання, хронологічно;
- № 676 р. I п. 8: строки – за Переліком типових документів (наказ Мін'юсту від 12.04.2012 № 578/5).

Строки за текстом Переліку 578/5 (копія з архіву hds-doc; номери статей у копії відсутні, тому поле
«Стаття» заповнює заклад за чинною редакцією на zakon.rada.gov.ua):
- накази з основної діяльності – постійно;
- з кадрових питань (особового складу) – 75 років; про короткострокові відрядження, стягнення,
  щорічні оплачувані відпустки й відпустки у зв'язку з навчанням – 5 років (примітка до статті);
- з адміністративно-господарських питань – 5 років;
- реєстраційні журнали розпорядчих документів: основна – постійно, кадрові – 75 р. (відпустки – 5 р.),
  адмін.-госп. – 5 р.
Для наказів з руху учнів окремої статті в Переліку не знайдено: строк визначає експертна комісія закладу.
"""
from __future__ import annotations

import datetime as dt
import os
import tempfile

from .db import KIND_BY_CODE, Database, format_date

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nomenclature (
    year INTEGER NOT NULL, kind TEXT NOT NULL, part TEXT NOT NULL DEFAULT 'orders',  -- orders | journal
    case_index TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, retention TEXT NOT NULL DEFAULT '',
    article TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (year, kind, part));
"""

DEFAULTS = {  # kind: (назва справи з наказами, строк, назва журналу, строк журналу, примітка)
    "osn": ("Накази директора з основної діяльності", "Пост.",
            "Журнал реєстрації наказів з основної діяльності", "Пост.", ""),
    "u": ("Накази директора з руху учнів", "",
          "Журнал реєстрації наказів з руху учнів", "",
          "Окремої статті в Переліку 578/5 не знайдено; строк визначає експертна комісія закладу"),
    "k": ("Накази директора з кадрових питань (особового складу) тривалого зберігання", "75 р.",
          "Журнал реєстрації наказів з кадрових питань тривалого зберігання", "75 р.", ""),
    "v": ("Накази директора з кадрових питань тимчасового зберігання (відпустки, відрядження, стягнення)", "5 р.",
          "Журнал реєстрації наказів з кадрових питань тимчасового зберігання", "5 р.", ""),
    "g": ("Накази директора з адміністративно-господарських питань", "5 р.",
          "Журнал реєстрації наказів з адміністративно-господарських питань", "5 р.", ""),
}


class Cases:
    def __init__(self, db: Database):
        self.db = db
        db.con.executescript(_SCHEMA)

    def ensure_year(self, year: int):
        """Номенклатура на рік: копія попереднього року (індекси й статті закладу) або типові значення."""
        if self.db.con.execute("SELECT 1 FROM nomenclature WHERE year = ?", (year,)).fetchone():
            return
        prev = self.db.con.execute("SELECT * FROM nomenclature WHERE year = (SELECT MAX(year) FROM nomenclature "
                                   "WHERE year < ?)", (year,)).fetchall()
        with self.db.tx():
            if prev:
                for r in prev:
                    self.db.con.execute("INSERT INTO nomenclature VALUES (?,?,?,?,?,?,?,?)",
                                        (year, r["kind"], r["part"], r["case_index"], r["title"], r["retention"],
                                         r["article"], r["note"]))
                return
            for i, (kind, (t, ret, jt, jret, note)) in enumerate(DEFAULTS.items(), 1):
                self.db.con.execute("INSERT INTO nomenclature VALUES (?,?,?,?,?,?,?,?)",
                                    (year, kind, "orders", f"01-{i:02d}", t, ret, "", note))
                self.db.con.execute("INSERT INTO nomenclature VALUES (?,?,?,?,?,?,?,?)",
                                    (year, kind, "journal", f"01-{i + 5:02d}", jt, jret, "", note))

    def items(self, year: int):
        self.ensure_year(year)
        return self.db.con.execute("SELECT * FROM nomenclature WHERE year = ? ORDER BY case_index, kind",
                                   (year,)).fetchall()

    def get(self, year: int, kind: str, part: str = "orders"):
        self.ensure_year(year)
        return self.db.con.execute("SELECT * FROM nomenclature WHERE year = ? AND kind = ? AND part = ?",
                                   (year, kind, part)).fetchone()

    def update(self, year: int, kind: str, part: str, **f):
        f = {k: v for k, v in f.items() if k in ("case_index", "title", "retention", "article", "note")}
        self.ensure_year(year)
        if f:
            with self.db.tx():
                self.db.con.execute(f"UPDATE nomenclature SET {', '.join(k + ' = ?' for k in f)} "
                                    "WHERE year = ? AND kind = ? AND part = ?", [*f.values(), year, kind, part])

    def problems(self, year: int) -> list[str]:
        out = []
        for r in self.items(year):
            if not r["retention"].strip():
                out.append(f"Справа «{r['title']}»: не вказано строк зберігання")
            if not r["case_index"].strip():
                out.append(f"Справа «{r['title']}»: не вказано індекс справи")
        idx = [r["case_index"] for r in self.items(year) if r["case_index"]]
        for d in sorted({i for i in idx if idx.count(i) > 1}):
            out.append(f"Індекс справи {d} повторюється")
        return out


def case_inventory_html(db: Database, kind: str, year: int) -> str:
    """Перелік наказів у справі (хронологічно, р. VI п. 3) – перша сторінка справи."""
    c = Cases(db).get(year, kind)
    rows = [o for o in db.journal(kind, year)]
    body = "".join(f"<tr><td>{i}</td><td>{o['reg_index']}</td><td>{format_date(o['date'])}</td>"
                   f"<td>{o['title']}{' (скасовано)' if o['status'] == 'cancelled' else ''}</td></tr>"
                   for i, o in enumerate(rows, 1))
    return (f"<p align=center><b>Справа № {c['case_index']}</b></p><p align=center><b>{c['title']}</b></p>"
            f"<p align=center>{year} рік · строк зберігання: {c['retention'] or '–'}"
            f"{' (ст. ' + c['article'] + ' Переліку 578/5)' if c['article'] else ''}</p>"
            "<table><tr><th>№ з/п</th><th>№ наказу</th><th>Дата</th><th>Заголовок</th></tr>"
            f"{body}</table>")


def export_case_pdf(db: Database, kind: str, year: int, path: str, progress=None) -> str:
    """Справа одним PDF: перелік наказів, далі накази з додатками в хронологічному порядку
    (№ 676 р. VI пп. 3–4). Архівні накази з PDF-оригіналом вставляються як є."""
    from pypdf import PdfReader, PdfWriter

    from shkola.export.html_docx import html_to_docx

    from .export import MARGINS, _html, append_file_attachments, build_docx, docx_to_pdf_many, format_tables
    tmp = tempfile.mkdtemp()
    inv = html_to_docx(_html(case_inventory_html(db, kind, year)), None, MARGINS)
    format_tables(inv, 14)
    inv_path = os.path.join(tmp, "000-inv.docx"); inv.save(inv_path)
    orders = db.journal(kind, year)
    plan, docx = [], [inv_path]
    for i, o in enumerate(orders):
        if progress:
            progress(i, len(orders) * 2)
        orig = db.original(o["id"]) if o["source"] == "import" else None
        if orig and orig["filename"].lower().endswith(".pdf"):
            p = os.path.join(tmp, f"{i + 1:04d}.pdf")
            with open(p, "wb") as fh:
                fh.write(orig["data"])
            plan.append((o, p))
        else:
            p = os.path.join(tmp, f"{i + 1:04d}.docx")
            build_docx(db, o["id"]).save(p)
            docx.append(p); plan.append((o, os.path.splitext(p)[0] + ".pdf"))
    if progress:
        progress(len(orders), len(orders) * 2)
    docx_to_pdf_many(docx)
    w = PdfWriter()
    w.append(PdfReader(os.path.splitext(inv_path)[0] + ".pdf"))
    for o, p in plan:
        w.append(PdfReader(p))
        append_file_attachments(db, o["id"], w)
    with open(path, "wb") as fh:
        w.write(fh)
    return path


_ = (dt, KIND_BY_CODE)
