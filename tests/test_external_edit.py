"""Текст наказу редагується в окремій програмі: «Офіс ШКОЛА» → програма Windows для DOCX → вибрана програма.
Зміни з DOCX повертаються в базу без втрат і без накопичення порожніх абзаців."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["NAKAZY_OFFLINE"] = "1"

from nakazy import external_edit as ee  # noqa: E402
from nakazy.db import Database, OrderLocked  # noqa: E402
from nakazy.ui.order_editor import create_from_template  # noqa: E402


class ExternalEditTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.db = Database(os.path.join(self.d, "e.db"))
        self.db.set_setting("head", "Олена ПЕТРЕНКО")

    def tearDown(self):
        self.db.close()

    def test_round_trip_stable(self):
        oid = create_from_template(self.db, "v_annual", {"employee": "Коваль Марії Іванівні", "days": "28"})
        self.db.update_draft(oid, body_html=self.db.get(oid)["body_html"] +
                             "<table border=1><tr><td>а</td><td><b>б</b></td></tr></table><p><i>курсив</i></p>")
        title0 = self.db.get(oid)["title"]
        path = ee.write_docx(self.db, oid)
        self.assertTrue(path.endswith(".docx") and os.path.dirname(path).endswith("edit"))
        ee.sync(self.db, oid, path)  # перше перетворення формату
        body1 = self.db.get(oid)["body_html"]
        for _ in range(3):  # повторне відкриття без правок нічого не змінює
            self.assertFalse(ee.sync(self.db, oid, ee.write_docx(self.db, oid)))
        self.assertEqual(self.db.get(oid)["body_html"], body1)
        row = self.db.get(oid)
        self.assertEqual(row["title"], title0)
        for s in ("НАКАЗУЮ:", "Коваль Марії Іванівні", "<b>б</b>", "<i>курсив</i>", "<table"):
            self.assertIn(s, row["body_html"])
        self.assertNotRegex(row["body_html"], r"<p[^>]*>(\s|<br/>)*</p>")

    def test_title_and_versions(self):
        import docx
        oid = create_from_template(self.db, "o_free", {"subject": "чергування"})
        path = ee.write_docx(self.db, oid)
        d = docx.Document(path); d.paragraphs[0].text = "Про чергування в грудні"; d.add_paragraph("Новий пункт.")
        d.save(path)
        n0 = len(self.db.versions(oid))
        self.assertTrue(ee.sync(self.db, oid, path))
        row = self.db.get(oid)
        self.assertEqual(row["title"], "Про чергування в грудні")
        self.assertIn("Новий пункт.", row["body_html"])
        self.assertGreater(len(self.db.versions(oid)), n0)

    def test_registered_locked(self):
        oid = create_from_template(self.db, "o_free", {"subject": "чергування"})
        path = ee.write_docx(self.db, oid)
        self.db.register(oid, "2026-11-17")
        import docx
        d = docx.Document(path); d.add_paragraph("Спроба змінити."); d.save(path)
        with self.assertRaises(OrderLocked):
            ee.sync(self.db, oid, path)
        copy = ee.write_docx(self.db, oid, copy=True)  # копія з бланком для перегляду
        self.assertIn("копія для перегляду", copy); self.assertTrue(os.path.getsize(copy) > 0)

    def test_editor_choice(self):
        path = os.path.join(self.d, "x.docx")
        with mock.patch.object(ee, "office_exe", return_value=r"C:\office\ofis-shkola.exe"), \
                mock.patch.object(ee.subprocess, "Popen") as po, mock.patch.object(ee.os, "startfile", create=True) as sf:
            self.assertEqual(ee.open_file(self.db, path), "Офіс ШКОЛА")
            po.assert_called_once_with([r"C:\office\ofis-shkola.exe", path]); sf.assert_not_called()
        with mock.patch.object(ee, "office_exe", return_value=None), \
                mock.patch.object(ee.os, "startfile", create=True) as sf:
            self.assertEqual(ee.open_file(self.db, path), "програма Windows для DOCX"); sf.assert_called_once_with(path)
        self.db.set_setting("editor", "system")
        with mock.patch.object(ee, "office_exe", return_value=r"C:\office\ofis-shkola.exe"), \
                mock.patch.object(ee.os, "startfile", create=True) as sf, mock.patch.object(ee.subprocess, "Popen") as po:
            ee.open_file(self.db, path); sf.assert_called_once(); po.assert_not_called()
        with mock.patch.object(ee.os, "startfile", side_effect=OSError(1155, "немає програми"), create=True):
            with self.assertRaises(ee.NoEditor):
                ee.open_file(self.db, path)
        exe = shutil.which("python") or sys.executable
        self.db.set_setting("editor", "custom"); self.db.set_setting("editor_path", exe)
        with mock.patch.object(ee.subprocess, "Popen") as po:
            ee.open_file(self.db, path); po.assert_called_once_with([exe, path])

    def test_no_editor_offers_store(self):
        from PySide6.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication([])
        from nakazy.ui.order_editor import OrderEditor
        oid = create_from_template(self.db, "o_free", {"subject": "чергування"})
        ed = OrderEditor(self.db, oid)
        with mock.patch("nakazy.external_edit.open_file", side_effect=ee.NoEditor("x")), \
                mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as q, \
                mock.patch("nakazy.ui.order_editor.QDesktopServices.openUrl", return_value=True) as ou:
            ed.start_edit()
        q.assert_called_once(); self.assertIn("9P6Q3GQW1SQF", ou.call_args[0][0].toString())
        ed.close()


from qt_cleanup import tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
