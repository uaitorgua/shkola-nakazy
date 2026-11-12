import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["NAKAZY_OFFLINE"] = "1"

from nakazy.audit import audit  # noqa: E402
from nakazy.cases import Cases, case_inventory_html, export_case_pdf  # noqa: E402
from nakazy.db import Database  # noqa: E402

BODY = "<p>…</p><p>НАКАЗУЮ:</p><p>1. …</p>"


class CasesTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.d, "c.db"))
        self.c = Cases(self.db)

    def test_defaults_and_copy_to_next_year(self):
        items = {(r["kind"], r["part"]): r for r in self.c.items(2026)}
        self.assertEqual(len(items), 10)
        self.assertEqual(items[("osn", "orders")]["retention"], "Пост.")
        self.assertEqual(items[("k", "orders")]["retention"], "75 р.")
        self.assertEqual(items[("v", "orders")]["retention"], "5 р.")
        self.assertEqual(items[("g", "journal")]["retention"], "5 р.")
        self.assertEqual(items[("u", "orders")]["retention"], "")       # статті немає: вирішує ЕК закладу
        self.assertTrue(any("руху учнів" in p for p in self.c.problems(2026)))
        self.c.update(2026, "u", "orders", retention="Пост.", case_index="02-01", article="ст. Х")
        self.c.update(2026, "u", "journal", retention="Пост.")
        r = self.c.get(2027, "u")                                     # новий рік копіює рішення закладу
        self.assertEqual((r["retention"], r["case_index"], r["article"]), ("Пост.", "02-01", "ст. Х"))

    def test_duplicate_index_warning(self):
        self.c.update(2026, "k", "orders", case_index="01-01")
        self.assertTrue(any("повторюється" in p for p in self.c.problems(2026)))
        oid = self.db.create_draft("k", title="Про прийняття", body_html=BODY, signer="Олена ПЕТРЕНКО")
        self.db.register(oid, "2026-03-01")
        self.assertTrue(any("Номенклатура 2026" in t and "повторюється" in t for _l, t in audit(self.db)))

    def test_case_pdf(self):
        for i in range(3):
            oid = self.db.create_draft("v", title=f"Про відпустку {i}", body_html=BODY, signer="Олена ПЕТРЕНКО")
            self.db.register(oid, f"2026-06-0{i + 1}")
        self.db.import_order("v", 10, "2026-07-01", "Про архівну відпустку", "<p>НАКАЗУЮ:</p>")
        html = case_inventory_html(self.db, "v", 2026)
        self.assertIn("5 р.", html); self.assertIn("10-в", html)
        try:
            p = export_case_pdf(self.db, "v", 2026, os.path.join(self.d, "case.pdf"))
        except RuntimeError as e:
            self.skipTest(str(e))
        from pypdf import PdfReader
        r = PdfReader(p)
        self.assertGreaterEqual(len(r.pages), 5)  # перелік + 4 накази
        self.assertIn("Справа", r.pages[0].extract_text())

    def test_dialog(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from nakazy.ui.cases_dialog import CasesDialog
        dlg = CasesDialog(None, self.db, 2026); dlg.show(); app.processEvents()
        self.assertEqual(dlg.table.rowCount(), 10)
        dlg.table.item(0, 3).setText("ст. 16 а")
        kind, part = dlg.table.item(0, 0).data(256)
        self.assertEqual(self.c.get(2026, kind, part)["article"], "ст. 16 а")


from qt_cleanup import tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
