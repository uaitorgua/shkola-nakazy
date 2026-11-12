import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from PIL import Image  # noqa: E402

from nakazy.db import Database  # noqa: E402
from nakazy.export import build_docx, export_pdf  # noqa: E402
from nakazy.templates import TEMPLATES  # noqa: E402
from nakazy.ui.order_editor import create_from_template  # noqa: E402

TABLE = "<table><tr><th>№</th><th>ПІБ</th></tr>" + "".join(
    f"<tr><td>{i}</td><td>Учень {i}</td></tr>" for i in range(1, 80)) + "</table>"


def png() -> bytes:
    b = io.BytesIO(); Image.new("RGB", (800, 200), "white").save(b, "PNG"); return b.getvalue()


def blank_docx() -> bytes:
    d = Document(); d.add_paragraph("ГЕРБ")
    d.add_paragraph().add_run().add_picture(io.BytesIO(png()))
    d.add_paragraph("ЛІЦЕЙ З БЛАНКА WORD")
    b = io.BytesIO(); d.save(b); return b.getvalue()


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.d, "e.db"))
        for k, v in dict(school="Ліцей № 1", head="Олена ПЕТРЕНКО", city="Дрогобич").items():
            self.db.set_setting(k, v)

    def order(self, tid="o_excursion"):
        oid = create_from_template(self.db, tid, {})
        atts = self.db.attachments(oid)
        if atts:
            self.db.con.execute("UPDATE attachments SET body_html = ? WHERE id = ?", (TABLE, atts[0]["id"]))
        self.db.register(oid, "2026-11-08")
        return oid

    def text(self, doc):
        return "\n".join(p.text for p in doc.paragraphs)

    def check_common(self, doc, oid):
        t = self.text(doc)
        self.assertIn("НАКАЗ", t)
        self.assertIn(f"№ {self.db.get(oid)['reg_index']}", t)
        self.assertIn("08.11.2026", t)
        self.assertIn("НАКАЗУЮ:", t)
        self.assertIn("Олена ПЕТРЕНКО", t)
        sec = doc.sections[0]
        self.assertTrue(sec.different_first_page_header_footer)  # перша сторінка без номера
        self.assertIn("PAGE", sec.header._element.xml)
        self.assertEqual(round(sec.left_margin.mm), 30); self.assertEqual(round(sec.right_margin.mm), 10)
        # порядок: бланк/НАКАЗ – дата – заголовок – текст
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        i_n = paras.index("НАКАЗ"); i_t = paras.index(self.db.get(oid)["title"])
        self.assertLess(i_n, i_t)
        self.assertLess(i_t, next(i for i, p in enumerate(paras) if p.startswith("НАКАЗУЮ")))

    def test_text_blank_and_attachment_table(self):
        self.db.save_blank("т", "text", None, {"owner": "МІСЬКА РАДА", "school": "ЛІЦЕЙ № 1", "address": "вул. 1"})
        oid = self.order()
        doc = build_docx(self.db, oid)
        self.check_common(doc, oid)
        self.assertEqual(self.text(doc).count("НАКАЗ\n"), 1)
        self.assertIn("Додаток 1", self.text(doc))
        self.assertIn("від 08.11.2026 № 1", self.text(doc))
        t = doc.tables[0]
        self.assertIn("w:tblHeader", t.rows[0]._tr.xml)
        self.assertIn("w:cantSplit", t.rows[5]._tr.xml)

    def test_dstu_details(self):
        from docx.shared import Mm, Pt
        from nakazy.export import dstu_signature
        self.assertEqual(dstu_signature("Петренко Олена Іванівна"), "Олена ПЕТРЕНКО")
        self.assertEqual(dstu_signature("Олена Петренко"), "Олена ПЕТРЕНКО")
        self.db.set_setting("acquaint", "1")
        oid = create_from_template(self.db, "o_attest", {})  # додатки затверджуються наказом
        self.db.update_draft(oid, responsible="Іваненко Петро Олегович, Олена Коваль")
        self.db.register(oid, "2026-11-08")
        doc = build_docx(self.db, oid)
        t = self.text(doc)
        sig = next(p for p in doc.paragraphs if p.text.startswith("Директор	"))
        self.assertEqual(round(sig.paragraph_format.tab_stops[0].position.mm), 125)
        self.assertIn("З наказом ознайомлені:", t)
        self.assertIn("Петро ІВАНЕНКО", t); self.assertIn("Олена КОВАЛЬ", t)
        self.assertIn("ЗАТВЕРДЖЕНО", t); self.assertNotIn("Додаток 1", t)
        grif = next(p for p in doc.paragraphs if p.text == "ЗАТВЕРДЖЕНО")
        self.assertEqual(round(grif.paragraph_format.left_indent.mm), 100)
        self.db.set_setting("grif_indent", "104")
        grif = next(p for p in build_docx(self.db, oid).paragraphs if p.text == "ЗАТВЕРДЖЕНО")
        self.assertEqual(round(grif.paragraph_format.left_indent.mm), 104)

    def test_table_font_not_below_12(self):
        from docx.shared import Pt
        self.db.set_setting("font_size", "12")
        oid = self.order()
        for row in build_docx(self.db, oid).tables[0].rows[:3]:
            for c in row.cells:
                for r in c.paragraphs[0].runs:
                    self.assertGreaterEqual(r.font.size, Pt(12))

    def test_image_blank(self):
        self.db.save_blank("і", "image", png(), {"width_mm": 170, "has_nakaz": False})
        oid = self.order()
        doc = build_docx(self.db, oid)
        self.check_common(doc, oid)
        self.assertTrue(any(p._p.xpath(".//pic:pic") for p in doc.paragraphs[:2]))

    def test_docx_blank_with_image(self):
        self.db.save_blank("w", "docx", blank_docx(), {"has_nakaz": False})
        oid = self.order()
        doc = build_docx(self.db, oid)
        self.check_common(doc, oid)
        self.assertEqual(doc.paragraphs[2].text, "ЛІЦЕЙ З БЛАНКА WORD")
        out = os.path.join(self.d, "w.docx"); doc.save(out)
        Document(out)  # файл відкривається, зображення герба не загублене
        rid = doc.paragraphs[1]._p.xpath(".//a:blip")[0].get(qn("r:embed"))
        self.assertIn(rid, doc.part.related_parts)

    def test_all_templates_export(self):
        for t in TEMPLATES:
            oid = create_from_template(self.db, t.id, {})
            doc = build_docx(self.db, oid)
            self.assertIn("НАКАЗУЮ:", self.text(doc), t.id)
            doc.save(os.path.join(self.d, f"{t.id}.docx"))

    def test_pdf(self):
        oid = self.order()
        self.db.con.execute("UPDATE attachments SET mode='file', filename='a.pdf', data=? WHERE order_id=?",
                            (self._pdf_bytes(), oid))
        try:
            path = export_pdf(self.db, oid, os.path.join(self.d, "o.pdf"))
        except RuntimeError as e:
            self.skipTest(str(e))
        from pypdf import PdfReader
        r = PdfReader(path)
        self.assertGreaterEqual(len(r.pages), 2)  # наказ + доданий PDF-додаток
        self.assertIn("НАКАЗ", r.pages[0].extract_text())

    def _pdf_bytes(self):
        b = io.BytesIO(); Image.new("RGB", (300, 400), "white").save(b, "PDF"); return b.getvalue()


from qt_cleanup import tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
