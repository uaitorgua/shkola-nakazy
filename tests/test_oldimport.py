import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["NAKAZY_OFFLINE"] = "1"

from docx import Document  # noqa: E402

from nakazy import oldimport  # noqa: E402
from nakazy.audit import audit  # noqa: E402
from nakazy.db import Database, OrderLocked, RegistrationError  # noqa: E402

SOFFICE = shutil.which("soffice") or (r"C:\Program Files\LibreOffice\program\soffice.exe"
                                      if os.path.exists(r"C:\Program Files\LibreOffice\program\soffice.exe") else None)


def make_docx(path, lines):
    d = Document()
    for x in lines:
        d.add_paragraph(x)
    d.save(path)
    return path


ORDER_A = ["Дрогобицька міська рада", "ЛІЦЕЙ № 1", "НАКАЗ", "05.09.2025          м. Дрогобич          № 15-к",
           "Про прийняття на роботу", "Іваненка Петра Олеговича", "Відповідно до заяви…", "НАКАЗУЮ:",
           "1. Прийняти …", "Директор                     Олена ПЕТРЕНКО"]
ORDER_B = ["НАКАЗ", "«12» вересня 2025 р.", "м. Дрогобич", "№ 3 - у",
           "Про зарахування учня до 5-А класу", "На підставі заяви…", "НАКАЗУЮ:", "1. Зарахувати…",
           "Директор Олена ПЕТРЕНКО"]
ORDER_C = ["Н А К А З", "01.10.2025 № 120", "Про організацію харчування учнів", "З метою…", "НАКАЗУЮ:", "1. …"]
ORDER_NOSUF = ["НАКАЗ", "02.06.2025 № 44", "Про надання щорічної основної відпустки Коваль М. І.", "НАКАЗУЮ:"]


class Parse(unittest.TestCase):
    def test_variants(self):
        a = oldimport.parse("\n".join(ORDER_A))
        self.assertEqual((a["number"], a["suffix"], a["kind"], a["date"]), (15, "к", "k", "2025-09-05"))
        self.assertEqual(a["title"], "Про прийняття на роботу Іваненка Петра Олеговича")
        self.assertEqual(a["signer"], "Олена ПЕТРЕНКО")
        b = oldimport.parse("\n".join(ORDER_B))
        self.assertEqual((b["number"], b["kind"], b["date"]), (3, "u", "2025-09-12"))
        c = oldimport.parse("\n".join(ORDER_C))
        self.assertEqual((c["number"], c["kind"], c["date"], c["sure"]["kind"]), (120, "osn", "2025-10-01", True))
        n = oldimport.parse("\n".join(ORDER_NOSUF))
        self.assertEqual(n["kind"], "v")              # вид за словом «відпустки»
        self.assertFalse(n["sure"]["kind"])           # але позначено «перевірити»

    def test_garbage(self):
        for t in ["", "НАКАЗ", "№", "Про", "32.13.2025 № 0", "\x00" * 10, "№ 99999999", "лист без реквізитів"]:
            oldimport.parse(t)


class Files(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.d, "o.db"))

    def test_docx_txt_and_import(self):
        pa = make_docx(os.path.join(self.d, "a.docx"), ORDER_A)
        pt = os.path.join(self.d, "b.txt"); open(pt, "wb").write("\r\n".join(ORDER_B).encode("cp1251"))
        items = [oldimport.parse_file(p) for p in oldimport.scan_folder(self.d)]
        self.assertEqual(sorted((p.reg_index, p.source) for p in items), [("15-к", "docx"), ("3-у", "txt")])
        for p in items:
            self.db.import_order(p.kind, p.number, p.date, p.title, p.body_html, p.signer,
                                 os.path.basename(p.path), open(p.path, "rb").read())
        # повтор того самого номера – відмова
        p = items[0]
        with self.assertRaises(RegistrationError):
            self.db.import_order(p.kind, p.number, p.date, p.title)
        # нові накази продовжують нумерацію після архівних
        oid = self.db.create_draft("k", title="Про звільнення", body_html="<p>НАКАЗУЮ:</p>", signer="О. П.")
        self.assertEqual(self.db.register(oid, "2025-09-20"), "16-к")
        # пошук по тексту архівного наказу
        self.assertTrue(self.db.list_orders(query="Іваненка"))
        # виправлення розпізнаного дозволене лише для імпортованих
        imp = [r for r in self.db.list_orders() if r["source"] == "import"][0]
        self.db.fix_imported(imp["id"], title="Про виправлений заголовок")
        self.assertEqual(self.db.get(imp["id"])["title"], "Про виправлений заголовок")
        with self.assertRaises(OrderLocked):
            self.db.fix_imported(oid, title="Про інше")
        self.assertIsNotNone(self.db.original(imp["id"]))
        self.assertEqual([x for x in audit(self.db, dt.date(2026, 1, 1)) if x[0] == "помилка"], [])

    def test_archive_with_gaps_is_warning_only(self):
        for n in (1, 2, 5):
            self.db.import_order("osn", n, f"2024-03-0{n}", f"Про {n}")
        found = audit(self.db, dt.date(2025, 1, 1))
        self.assertEqual([x for x in found if x[0] == "помилка"], [])
        self.assertTrue(any("пропуски" in t for _l, t in found))

    @unittest.skipUnless(SOFFICE, "немає LibreOffice")
    def test_doc_and_pdf(self):
        pa = make_docx(os.path.join(self.d, "a.docx"), ORDER_A)
        out = os.path.join(self.d, "conv"); os.makedirs(out)
        subprocess.run([SOFFICE, "--headless", "--convert-to", "doc", "--outdir", out, pa], check=True, capture_output=True)
        subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", out, pa], check=True, capture_output=True)
        for ext, src in ((".doc", "doc"), (".pdf", "pdf-text")):
            p = oldimport.parse_file(os.path.join(out, "a" + ext))
            self.assertEqual((p.error, p.reg_index, p.date, p.source), ("", "15-к", "2025-09-05", src), ext)

    def test_scan_ocr(self):
        engine = oldimport._ocr_ready()
        if not engine.available():
            self.skipTest("немає моделей OCR")
        from PIL import Image, ImageDraw, ImageFont
        font = None
        for f in (r"C:\Windows\Fonts\times.ttf", r"C:\Windows\Fonts\arial.ttf"):
            if os.path.exists(f):
                font = ImageFont.truetype(f, 44); break
        if not font:
            self.skipTest("немає шрифту")
        img = Image.new("RGB", (2480, 1400), "white"); dr = ImageDraw.Draw(img)
        y = 150
        for line in ["НАКАЗ", "05.09.2025                 м. Дрогобич                 № 15-к",
                     "Про прийняття на роботу Іваненка Петра", "НАКАЗУЮ:", "1. Прийняти на посаду вчителя."]:
            dr.text((300, y), line, fill="black", font=font); y += 110
        path = os.path.join(self.d, "scan.png"); img.save(path, dpi=(300, 300))
        p = oldimport.parse_file(path)
        self.assertEqual(p.source, "ocr")
        self.assertEqual(p.date, "2025-09-05", p.text)
        self.assertEqual(p.number, 15, p.text)
        self.assertTrue(p.title.startswith("Про прийняття"), p.text)
        self.assertIn("скан: звірити текст", oldimport.problems(p))


class Gui(unittest.TestCase):
    def test_dialog(self):
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication([])
        from nakazy.ui.oldimport_dialog import OldImportDialog
        from nakazy.ui.order_editor import OrderEditor
        d = tempfile.mkdtemp(); db = Database(os.path.join(d, "g.db"))
        pa = make_docx(os.path.join(d, "a.docx"), ORDER_A)
        pc = make_docx(os.path.join(d, "c.docx"), ["Просто лист без реквізитів"])
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        dlg = OldImportDialog(None, db); dlg.load([pa, pc])
        self.assertEqual(dlg.table.rowCount(), 2)
        # секретар виправляє нерозпізнане в другому рядку
        dlg.table.cellWidget(1, 2).setValue(7)
        dlg.table.cellWidget(1, 3).setDate(dlg.table.cellWidget(1, 3).date().fromString("2025-10-02", "yyyy-MM-dd"))
        dlg.table.cellWidget(1, 4).setText("Про лист управління")
        dlg.apply()
        self.assertEqual(sorted(r["reg_index"] for r in db.list_orders()), ["15-к", "7"])
        oid = [r for r in db.list_orders() if r["reg_index"] == "7"][0]["id"]
        ed = OrderEditor(db, oid); app.processEvents()
        self.assertFalse(ed.edit.isReadOnly())
        ed.edit.setPlainText("Виправлений текст"); ed.save_fix()
        self.assertIn("Виправлений текст", db.get(oid)["body_html"])


if __name__ == "__main__":
    unittest.main()
